# linear_optimizer.py
import pulp
import json
import pandas as pd
import math
import logging
from datetime import datetime

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,  # Default logging level
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],  # Log to stdout for Docker compatibility
)
logger = logging.getLogger(__name__)


def run_optimization(
    forecast_data_json, initial_soc_percent, current_time_index, battery_params
):
    """
    Runs the battery schedule optimization.

    Args:
        forecast_data_json (str): JSON string containing the forecast data.
        initial_soc_percent (float): Current battery SOC (0-100).
        current_time_index (int): The starting index in the forecast data.
        battery_params (dict): Dictionary with battery parameters like
                               'capacity_kwh', 'max_rate_kw',
                               'min_soc_percent', 'efficiency_roundtrip'.

    Returns:
        tuple: (status_string, results_df | None, action_now | None, total_savings | None)
               Returns optimization status, DataFrame with the schedule,
               the action for the immediate next hour, and total savings.
               Returns None for DataFrame, action, and savings if optimization fails.
    """
    try:
        forecast_data = json.loads(forecast_data_json)["data"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing forecast data: {e}")
        return f"Error parsing forecast data: {e}", None, None, None

    # Battery Parameters from dict
    try:
        BATT_CAPACITY_KWH = float(battery_params["capacity_kwh"])
        BATT_MAX_RATE_KW = float(battery_params["max_rate_kw"])
        BATT_MIN_SOC_PERCENT = float(battery_params["min_soc_percent"])
        BATT_EFFICIENCY_ROUNDTRIP = float(battery_params["efficiency_roundtrip"])
    except (KeyError, ValueError) as e:
        logger.error(f"Error parsing battery parameters: {e}")
        return f"Error parsing battery parameters: {e}", None, None, None

    # Simulation Parameters
    CURRENT_SOC_PERCENT = float(initial_soc_percent)
    CURRENT_TIME_INDEX = int(current_time_index)

    # Derived Parameters
    BATT_MIN_SOC_KWH = BATT_CAPACITY_KWH * (BATT_MIN_SOC_PERCENT / 100.0)
    BATT_MAX_SOC_KWH = BATT_CAPACITY_KWH
    INITIAL_SOC_KWH = BATT_CAPACITY_KWH * (CURRENT_SOC_PERCENT / 100.0)
    if INITIAL_SOC_KWH < BATT_MIN_SOC_KWH:
        INITIAL_SOC_KWH = BATT_MIN_SOC_KWH  # Ensure initial SOC is not below min
    if INITIAL_SOC_KWH > BATT_MAX_SOC_KWH:
        INITIAL_SOC_KWH = BATT_MAX_SOC_KWH  # Ensure initial SOC is not above max
    try:
        BATT_EFFICIENCY_ONEWAY = math.sqrt(BATT_EFFICIENCY_ROUNDTRIP)
        INV_BATT_EFFICIENCY_ONEWAY = 1.0 / BATT_EFFICIENCY_ONEWAY
    except ValueError:
        logger.error("Error calculating efficiency (sqrt negative?)")
        return f"Error calculating efficiency (sqrt negative?)", None, None, None
    except ZeroDivisionError:
        logger.error("Error calculating efficiency (zero efficiency?)")
        return f"Error calculating efficiency (zero efficiency?)", None, None, None

    BATT_MAX_ENERGY_PER_STEP = BATT_MAX_RATE_KW * 1.0  # Energy in 1 hour

    # Extract relevant forecast data
    try:
        prices = {item["index"]: float(item["adjustedPrice"]) for item in forecast_data}
        hours = {item["index"]: item["hour"] for item in forecast_data}
        dates = {item["index"]: item["date"] for item in forecast_data}
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error processing forecast data fields: {e}")
        return f"Error processing forecast data fields: {e}", None, None, None

    indices = sorted(prices.keys())

    # Filter indices for the optimization period
    optimization_indices = [i for i in indices if i >= CURRENT_TIME_INDEX]
    if not optimization_indices:
        logger.error("No future time steps found for optimization.")
        return "No future time steps found for optimization.", None, None, None

    # Number of time steps in optimization horizon
    T = len(optimization_indices)
    opt_idx_map = {
        t: optimization_indices[t] for t in range(T)
    }  # Map step t to original index

    # --- Logging Parameters ---
    logger.debug("--- Running Optimization ---")
    logger.debug(f"Battery Capacity: {BATT_CAPACITY_KWH} kWh")
    logger.debug(f"Min SOC: {BATT_MIN_SOC_PERCENT}% ({BATT_MIN_SOC_KWH:.2f} kWh)")
    logger.debug(f"Max Charge/Discharge Rate: {BATT_MAX_RATE_KW} kW")
    logger.debug(
        f"Round-trip Efficiency: {BATT_EFFICIENCY_ROUNDTRIP*100:.1f}% (One-way: {BATT_EFFICIENCY_ONEWAY*100:.1f}%)"
    )
    logger.debug(
        f"Current Time Index: {CURRENT_TIME_INDEX} (Hour {hours.get(CURRENT_TIME_INDEX, 'N/A')})"
    )
    logger.debug(f"Initial SOC: {CURRENT_SOC_PERCENT}% ({INITIAL_SOC_KWH:.2f} kWh)")
    logger.debug(
        f"Optimization Horizon: {T} hours (Indices {optimization_indices[0]} to {optimization_indices[-1]})"
    )
    logger.debug("-------------------------")
    # --- End Logging ---

    # Create the MILP Problem
    prob = pulp.LpProblem("Battery_Schedule_Optimization", pulp.LpMaximize)

    # Define Decision Variables
    time_steps = range(T)
    charge_vars = pulp.LpVariable.dicts(
        "Charge",
        time_steps,
        lowBound=0,
        upBound=BATT_MAX_ENERGY_PER_STEP,
        cat="Continuous",
    )
    discharge_vars = pulp.LpVariable.dicts(
        "Discharge",
        time_steps,
        lowBound=0,
        upBound=BATT_MAX_ENERGY_PER_STEP,
        cat="Continuous",
    )
    soc_vars = pulp.LpVariable.dicts(
        "SOC",
        time_steps,
        lowBound=BATT_MIN_SOC_KWH,
        upBound=BATT_MAX_SOC_KWH,
        cat="Continuous",
    )
    is_charging = pulp.LpVariable.dicts("IsCharging", time_steps, cat="Binary")
    is_discharging = pulp.LpVariable.dicts("IsDischarging", time_steps, cat="Binary")

    # Define Objective Function (Maximize Savings)
    prob += (
        pulp.lpSum(
            discharge_vars[t] * prices[opt_idx_map[t]]
            - charge_vars[t] * prices[opt_idx_map[t]]
            for t in time_steps
        ),
        "Total Savings",
    )

    # Define Constraints
    for t in time_steps:
        idx = opt_idx_map[t]  # Original forecast index for this step

        # SOC Balance Constraint
        if t == 0:
            prob += (
                soc_vars[t]
                == INITIAL_SOC_KWH
                + charge_vars[t] * BATT_EFFICIENCY_ONEWAY
                - discharge_vars[t] * INV_BATT_EFFICIENCY_ONEWAY,
                f"SOC_Balance_{t}",
            )
        else:
            prob += (
                soc_vars[t]
                == soc_vars[t - 1]
                + charge_vars[t] * BATT_EFFICIENCY_ONEWAY
                - discharge_vars[t] * INV_BATT_EFFICIENCY_ONEWAY,
                f"SOC_Balance_{t}",
            )

        # Enforce Charge/Discharge Rate Limits using Binary Variables
        prob += (
            charge_vars[t] <= is_charging[t] * BATT_MAX_ENERGY_PER_STEP,
            f"Charge_Rate_{t}",
        )
        prob += (
            discharge_vars[t] <= is_discharging[t] * BATT_MAX_ENERGY_PER_STEP,
            f"Discharge_Rate_{t}",
        )

        # Mutual Exclusivity Constraint
        prob += is_charging[t] + is_discharging[t] <= 1, f"Mutual_Exclusivity_{t}"

    # Solve the Problem
    logger.info("Solving the optimization problem...")
    solver = pulp.PULP_CBC_CMD(msg=0)  # Suppress solver messages
    status = prob.solve(solver)
    status_string = pulp.LpStatus[status]
    logger.info(f"Solver Status: {status_string}")

    # Extract and Analyze Results
    results = []
    action_now = 0  # Default action
    total_savings = 0.0

    if status_string == "Optimal":
        total_savings = pulp.value(prob.objective)
        logger.info(f"Optimal Schedule Found! Max Savings: {total_savings:.4f}")

        # Determine action for the next hour (t=0)
        next_charge = charge_vars[0].varValue
        next_discharge = discharge_vars[0].varValue
        if next_charge > 0.01:
            action_now = next_charge
        elif next_discharge > 0.01:
            action_now = -1 * next_discharge

        logger.info(
            f"Action for Next Hour (Index {optimization_indices[0]}): {action_now}"
        )

        # Compile detailed plan
        cumulative_saving = 0
        for t in time_steps:
            idx = opt_idx_map[t]
            charge = charge_vars[t].varValue if charge_vars[t].varValue else 0.0
            discharge = (
                discharge_vars[t].varValue if discharge_vars[t].varValue else 0.0
            )
            soc = (
                soc_vars[t].varValue if soc_vars[t].varValue else BATT_MIN_SOC_KWH
            )  # Handle potential None
            price = prices[idx]
            hourly_saving = (discharge * price) - (charge * price)
            cumulative_saving += hourly_saving

            action = "Hold"
            energy = 0.0
            change_rate = 0.0
            if charge > 0.01:
                action = "Charge"
                energy = charge
                change_rate = (
                    energy / BATT_MAX_ENERGY_PER_STEP
                    if BATT_MAX_ENERGY_PER_STEP > 0
                    else 0
                )
            elif discharge > 0.01:
                action = "Discharge"
                energy = -discharge  # Show discharge as negative
                change_rate = (
                    energy / BATT_MAX_ENERGY_PER_STEP
                    if BATT_MAX_ENERGY_PER_STEP > 0
                    else 0
                )

            results.append(
                {
                    "Index": idx,
                    "Hour": hours[idx],
                    "Date": dates[idx],
                    "Price": price,
                    "Action": action,
                    "Energy_kWh": round(energy, 4),
                    "ChangeRate": f"{change_rate:.2f}",
                    "SOC_End_Percent": round((soc / BATT_CAPACITY_KWH) * 100.0, 2),
                    "Hourly_Saving": round(hourly_saving, 4),
                    "Cumulative_Saving": round(cumulative_saving, 4),
                }
            )

        # Summarize the next 12 hours plan
        next_12_hours_plan = []
        for t in range(min(12, len(time_steps))):  # Limit to the next 12 hours
            idx = opt_idx_map[t]
            charge = charge_vars[t].varValue if charge_vars[t].varValue else 0.0
            discharge = (
                discharge_vars[t].varValue if discharge_vars[t].varValue else 0.0
            )

            if charge > 0.01:
                next_12_hours_plan.append(f"Hour {hours[idx]}: Charge {charge:.2f} kWh")
            elif discharge > 0.01:
                next_12_hours_plan.append(
                    f"Hour {hours[idx]}: Discharge {discharge:.2f} kWh"
                )
            else:
                next_12_hours_plan.append(f"Hour {hours[idx]}: Hold")

        # Log the summarized 12-hour plan
        logger.info("Next 12-hour plan: " + " | ".join(next_12_hours_plan))

        results_df = pd.DataFrame(results)
        logger.debug("--- Optimal Plan Generated ---")
        return status_string, results_df, action_now, total_savings

    else:
        logger.warning(
            f"Solver did not find an optimal solution. Status: {status_string}"
        )
        return status_string, None, None, None
