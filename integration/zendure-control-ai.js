const IOBROKER = true;
const mockCurrentIndex = 18;
const mockSocValue = 0;

const debug = true;

const controlSecs = 15;

const { execSync } = require('child_process');

const adjustedPricesState = "0_userdata.0.tibber_adjusted_prices";

const currentTibberPrice = "tibberlink.0.Homes.<home-id>.CurrentPrice.total";

const acMode = "zendure-solarflow.0.<device-id>.control.acMode";
const inputLimit = "zendure-solarflow.0.<device-id>.control.setInputLimit";
const outputLimit = "zendure-solarflow.0.<device-id>.control.setOutputLimit";
const soc = "zendure-solarflow.0.<device-id>.electricLevel";
const batteryInputRealState = "zendure-solarflow.0.<device-id>.gridInputPower";
const batteryOutputRealState = "zendure-solarflow.0.<device-id>.packInputPower";

const socAtStartOfHourWhState = "0_userdata.0.zendure_start_hour_wh";
const currentChargeModeState = "0_userdata.0.zendure_current_charge_mode";

const overflowPowerState = "hass.0.entities.sensor.power_production_overflow_pv_only_household.state";
const householdConsumptionState = "hass.0.entities.sensor.power_consumption_household.state";
const pvPositifState = "hass.0.entities.sensor.power_production_pv.state";

const setZendureBuyPriceState = "hass.0.entities.input_number.energy_storage_zendure_battery_buy_price.set_value";
const setZendureSellPriceState = "hass.0.entities.input_number.energy_storage_zendure_battery_sell_price.set_value";
const setZendureBenefitPriceState = "hass.0.entities.input_number.energy_storage_zendure_battery_benefit_price.set_value";

const setPlanState = "hass.0.entities.input_text.power_storage_plan.set_value";

const batteryControlOverrideState = "hass.0.entities.input_boolean.zendure_battery_control_override.state";
const batteryOverridePowerState = "hass.0.entities.input_number.zendure_battery_power_override.state";

const BATTERY_CHARACTERISTICS = {
    capacity: 4 * 1900, // Battery capacity in Wh
    maxChargeRate: 1200, // Maximum charge rate in W
    maxDischargeRate: 1200, // Maximum discharge rate in W
    efficiency: 0.94, // 94% efficient
    minSoc: 0.05, // Minimum percentage
    maxSoc: 0.99,
    maintenanceSoc: 0.10, // Maintenance charge percentage
    maintenanceChargePower: 300 // Charge power for maintenance charging in W
};

function lg(message, onlyDebug) {
    if (onlyDebug && !debug) { return; }
    if (IOBROKER) { log(message, (onlyDebug ? 'debug' : 'info')); }
    else { console.log(message); }
}

// Function to read the adjusted prices data
function readAdjustedPrices() {

    if (!IOBROKER) {
        return readAdjustedPricesMock();
    }

    // Get the state value
    const stateValue = getState(adjustedPricesState).val;

    // Parse the JSON data
    let adjustedPrices;
    try {
        adjustedPrices = JSON.parse(stateValue).data;
    } catch (error) {
        lg(`Failed to parse adjusted prices JSON: ${error.message}`);
        return [];
    }

    // Validate the structure of the data
    if (!Array.isArray(adjustedPrices)) {
        lg("Adjusted prices data is not an array.");
        return [];
    }

    //console.log("Successfully read adjusted prices:");
    //console.log(JSON.stringify(adjustedPrices, null, 2));

    return adjustedPrices;
}

function readAdjustedPricesMock() {
    // read mock data from file
    const fs = require("fs");
    const path = require("path");
    const filePath = path.join(__dirname, "mock.json");
    const fileContent = fs.readFileSync(filePath, "utf8");
    return JSON.parse(fileContent);
}

function getCurrentIndex(prices) {
    const now = new Date();
    const currentHour = now.getHours();
    const currentDate = now.toISOString().split("T")[0]; // Format date as YYYY-MM-DD

    // Find the index in the prices array
    const currentIndex = prices.findIndex(entry => entry.hour === currentHour && entry.date === currentDate);

    if (currentIndex === -1) {
        throw new Error("Current index not found in the provided data.");
    }

    return currentIndex;
}

function GetCurrentSoc() {
    // calculate soc in Wh
    let socValue = 0;
    if (IOBROKER) { socValue = getState(soc).val; }
    else { socValue = mockSocValue; }
    const socWh = BATTERY_CHARACTERISTICS.capacity * socValue / 100;
    return socWh;
}


function GetActionFromAi(currentIndex) {
    if (!IOBROKER) {
        return { plannedCharge: 0, plannedDischarge: 0 }; // Mocked response
    }

    const currentSoc = GetCurrentSoc() / BATTERY_CHARACTERISTICS.capacity;
    const requestBody = JSON.stringify({
        current_soc_percent: currentSoc * 100,
        current_time_index: currentIndex,
        battery_params: {
            capacity_kwh: BATTERY_CHARACTERISTICS.capacity / 1000,
            max_rate_kw: BATTERY_CHARACTERISTICS.maxChargeRate / 1000,
            min_soc_percent: BATTERY_CHARACTERISTICS.maintenanceSoc * 100,
            efficiency_roundtrip: BATTERY_CHARACTERISTICS.efficiency
        }
    });

    lg(`AI Body: ${requestBody}`, true);

    const url = "http://bear.cyberdns.org:5321/optimize";
    const command = `curl -s -X POST -H "Content-Type: application/json" -d '${requestBody}' ${url}`;

    try {
        const response = execSync(command, { encoding: 'utf8' });
        const body = JSON.parse(response);

        if (body && body.action_next_hour !== undefined) {
            lg(`AI Response: ${JSON.stringify(body)}`, true);
            return {
                plannedDischarge: -1 * Math.min(body.action_next_hour, 0) * 1000,
                plannedCharge: Math.max(body.action_next_hour, 0) * 1000
            };
        } else {
            lg("Invalid AI response format", true);
        }
    } catch (error) {
        lg(`AI request error: ${error.message}`, true);
    }

    return { plannedCharge: 0, plannedDischarge: 0 };
}





let maintenanceMode = false;

Calculate();
ControlCharge();


if (IOBROKER) {
    schedule({ minute: [0] }, Calculate);
    schedule(`*/${controlSecs} * * * * *`, ControlCharge);
}




function Calculate() {

    const socWh = GetCurrentSoc();

    if (IOBROKER) {
        setState(socAtStartOfHourWhState, socWh, false);
    }
}



function SetCharge(power, currentTotalPrice, chargeMode) {
    if (IOBROKER) {

        if (power > 0) {
            setState(acMode, 1, false);
            setState(inputLimit, power, false);
            setState(outputLimit, 0, false);
        } else if (power < 0) {
            setState(acMode, 2, false);
            setState(inputLimit, 0, false);
            setState(outputLimit, -1 * power, false);
        }
        else {
            setState(inputLimit, 0, false);
            setState(outputLimit, 0, false);
        }

        let realInputPower = getState(batteryInputRealState).val;
        let realOutputPower = getState(batteryOutputRealState).val;

        if (realInputPower > 0) {
            let overflowPower = Math.max(parseFloat(getState(overflowPowerState).val), 0);

            let powerWithPriceTag = Math.max(realInputPower - overflowPower, 0);
            lg(`Math.max(Math.abs(${realInputPower}) - ${overflowPower}, 0) = ${powerWithPriceTag}`, true);

            let priceForTimeslot = (powerWithPriceTag / 1000) * (currentTotalPrice / 3600);
            lg(`${priceForTimeslot} = (${powerWithPriceTag} / 1000) * (${currentTotalPrice} / 3600)`);

            setState(setZendureBuyPriceState, priceForTimeslot, false);
            setState(setZendureBenefitPriceState, -1 * priceForTimeslot, false);
        }
        else if (realOutputPower > 0) {
            let powerWithPriceTag = Math.max(realOutputPower - 10, 0); // The battery is reporting 10 W constantly 
            let priceForTimeslot = (powerWithPriceTag / 1000) * (currentTotalPrice / 3600);
            lg(`${priceForTimeslot} = (${powerWithPriceTag} / 1000) * (${currentTotalPrice} / 3600)`);

            setState(setZendureSellPriceState, priceForTimeslot, false);
            setState(setZendureBenefitPriceState, priceForTimeslot, false);
        }
        else {
            setState(setZendureSellPriceState, 0, false);
            setState(setZendureBenefitPriceState, 0, false);
        }

        setState(currentChargeModeState, chargeMode, false);
        lg(`Mode: "${chargeMode}" Request: ${power}W Real(In/Out): ${realInputPower}/${realOutputPower}W`, true);
    }
}

function ControlCharge() {
    const prices = readAdjustedPrices();
    const socWh = GetCurrentSoc();

    let socAtStartOfHourWh = socWh;
    let currentIndex = 0;
    let overflowPower = 0;

    let batteryControlOverride = 'off';
    let batteryOverridePower = 0;
    let currentTotalPrice = 0;
    if (IOBROKER) {
        currentIndex = getCurrentIndex(prices);
        overflowPower = parseFloat(getState(overflowPowerState).val);
        socAtStartOfHourWh = getState(socAtStartOfHourWhState).val;
        batteryControlOverride = getState(batteryControlOverrideState).val;
        batteryOverridePower = parseFloat(getState(batteryOverridePowerState).val);
        currentTotalPrice = getState(currentTibberPrice).val;
    } else {
        currentIndex = mockCurrentIndex;
    }

    // take the value for the current hour
    const currentHour = GetActionFromAi(currentIndex);
    lg(`Planned Charge: ${currentHour.plannedCharge}W Planned Discharge ${currentHour.plannedDischarge}W`, true);

    const currentMinute = new Date().getMinutes();
    const percentOfHourFinished = currentMinute / 60;

    if (socWh < BATTERY_CHARACTERISTICS.capacity * BATTERY_CHARACTERISTICS.minSoc) {
        maintenanceMode = true;
    }
    else if (socWh >= BATTERY_CHARACTERISTICS.capacity * BATTERY_CHARACTERISTICS.maintenanceSoc) {
        maintenanceMode = false;
    }

    let maintenanceChargePower = BATTERY_CHARACTERISTICS.maintenanceChargePower;
    if (maintenanceMode && (currentHour.plannedCharge < maintenanceChargePower)) {
        SetCharge(maintenanceChargePower, currentTotalPrice, "Maintenance charging");
    }
    else if (batteryControlOverride === 'on') {
        SetCharge(batteryOverridePower, currentTotalPrice, "Override");
    }
    else if (currentHour.plannedDischarge > 0) {
        let currentOutputLimit = 0;
        if (IOBROKER) { currentOutputLimit = getState(outputLimit).val; }
        lg("currentOutputLimit: " + currentOutputLimit, true);

        const alreadyDischarged = Math.max(socAtStartOfHourWh - socWh, 0);
        lg("alreadyDischarged: " + alreadyDischarged, true);

        const remainingEnergy = Math.max(currentHour.plannedDischarge - alreadyDischarged, 0);
        lg("remainingEnergy: " + remainingEnergy, true);

        const adjustedOverflowPower = overflowPower - currentOutputLimit;
        if (adjustedOverflowPower > 0) {
            SetCharge(adjustedOverflowPower, currentTotalPrice, "Overflow during planned discharge");
        }
        else {
            const maxPowerToApply = remainingEnergy * (1 / (1 - percentOfHourFinished));
            let actualDischargePower = 0;
            if (IOBROKER) {
                const pvPositif = getState(pvPositifState).val;
                const householdConsumption = getState(householdConsumptionState).val;
                lg("Household Consumption: " + householdConsumption, true);
                actualDischargePower = Math.min(householdConsumption, maxPowerToApply);
                actualDischargePower = actualDischargePower - pvPositif;
            }
            actualDischargePower = Math.min(actualDischargePower, BATTERY_CHARACTERISTICS.maxDischargeRate);
            SetCharge(-1 * actualDischargePower, currentTotalPrice, "Planned discharge");
        }
    }
    else if (socWh >= BATTERY_CHARACTERISTICS.capacity * BATTERY_CHARACTERISTICS.maxSoc) {
        SetCharge(0, currentTotalPrice, "Max SOC");
    }
    else if (currentHour.plannedCharge > 0) {
        let currentInputLimit = 0;
        if (IOBROKER) { currentInputLimit = getState(inputLimit).val; }

        const alreadyCharged = socWh - socAtStartOfHourWh;
        lg("alreadCharged: " + alreadyCharged, true);

        const minimalChargePower = Math.max(Math.min(
            (currentHour.plannedCharge - alreadyCharged) * (1 / (1 - percentOfHourFinished)),
            BATTERY_CHARACTERISTICS.maxChargeRate)
            , 0)
            * (2 - BATTERY_CHARACTERISTICS.efficiency);
        lg("minimalChargePower: " + minimalChargePower, true);

        const adjustedOverflowPower = overflowPower + currentInputLimit;
        lg("adjustedOverflowPower: " + adjustedOverflowPower, true);

        let actualChargePower = minimalChargePower;
        if (adjustedOverflowPower > 0) { actualChargePower = Math.max(minimalChargePower, adjustedOverflowPower); }

        SetCharge(actualChargePower, currentTotalPrice, "Planned charge");
    }
    else {

        if (overflowPower > 0) {
            SetCharge(overflowPower, currentTotalPrice, "Overflow charge");
        }
        else {
            SetCharge(0, currentTotalPrice, "No action");
        }

    }
}