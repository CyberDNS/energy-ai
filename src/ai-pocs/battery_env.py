import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces


class BatteryEnv(gym.Env):
    """Custom Gym environment for battery charging optimization using real electricity price data."""

    def __init__(
        self,
        price_data_path,
        inference_mode=False,
        start_soc=0,
        start_step=0,
        max_change_rate=0.5,
    ):
        super(BatteryEnv, self).__init__()

        self.price_data = pd.read_json(price_data_path)[
            "data"]  # Load JSON price data
        self.max_data_points = 48
        self.max_change_rate = max_change_rate
        self.current_step = 0
        self.inference_mode = inference_mode
        self.start_soc = start_soc
        self.start_step = start_step

        # Calculate mean price for the complete data
        self.min_price = np.min(
            [
                float(self.price_data[i]["adjustedPrice"])
                for i in range(0, len(self.price_data))
            ]
        )

        self.max_price = np.max(
            [
                float(self.price_data[i]["adjustedPrice"])
                for i in range(0, len(self.price_data))
            ]
        )

        self.observation_space = spaces.Box(
            low=np.array(
                [0.0]
                + [0.0]
                + [0.0]
                + [0.0] * self.max_data_points
                + [0.0] * self.max_data_points,
                dtype=np.float32,
            ),
            high=np.array(
                [1.0]
                + [1.0]
                + [self.max_data_points]
                + [1.0] * self.max_data_points
                + [1.0] * self.max_data_points,
                dtype=np.float32,
            ),
            dtype=np.float32,
        )

        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(1,), dtype=np.float32)

    def reset(self, seed=None, options=None):
        """Reset the environment at the beginning of an episode."""
        if not self.inference_mode:
            # self.current_step = np.random.randint(0, len(self.price_data) - 1)
            self.current_step = self.start_step
            # self.soc = np.random.uniform(0.2, 0.8)  # Random initial SoC
            self.soc = 0
            self.max_change_rate = np.random.uniform(0.1, 0.5)

        else:
            self.current_step = self.start_step
            self.soc = self.start_soc

        self.balance = 0.0

        return self._get_observation(), {}

    def _get_observation(self):
        """Return the current observation state."""
        all_prices = [
            (
                self.normalize_price(
                    float(self.price_data[i]["adjustedPrice"]))
                if i < len(self.price_data)
                else 0.5
            )
            for i in range(self.max_data_points)
        ]
        has_value = [
            1.0 if i < len(self.price_data) else 0.0
            for i in range(self.max_data_points)
        ]

        return np.concatenate(
            (
                [self.soc],
                [self.max_change_rate],
                [self.current_step],
                np.array(all_prices, dtype=np.float32),
                np.array(has_value, dtype=np.float32),
            )
        )
    # Normalize the price

    def normalize_price(self, price):
        return (price - self.min_price) / (self.max_price - self.min_price)

    def step(self, action):
        """Apply the agent's action and calculate the reward."""

        # Ensure the episode lasts exactly 48 steps
        done = self.current_step >= len(self.price_data) - 13

        change_rate = action[0] * self.max_change_rate
        change_rate_normalized = change_rate / self.max_change_rate

        current_price = self.normalize_price(float(
            self.price_data[self.current_step]["adjustedPrice"]))

        # Define penalty weights
        cycle_penalty = 0.01  # Small penalty for unnecessary cycling
        constraint_penalty = 10  # Large penalty for violating battery limits

        # Charge cost: If action > 0, we are charging (negative reward)
        charge_cost = -max(0, change_rate_normalized) * current_price

        # Discharge profit: If action < 0, we are selling energy (positive reward)
        discharge_profit = -min(0, change_rate_normalized) * current_price

        # Battery cycle penalty
        battery_wear = cycle_penalty * abs(change_rate_normalized)

        # Enforce constraints
        self.soc += change_rate
        constraint_violation = 0
        if self.soc > 1.0 or self.soc < 0.0:
            constraint_violation = constraint_penalty

        # Compute total reward
        reward = charge_cost + discharge_profit - battery_wear - constraint_violation

        self.balance += reward

        self.soc = np.clip(self.soc, 0, 1)

        # if self.inference_mode:
        #     # Debug prints
        #     print(f"Step: {self.current_step}")
        #     print(f"Action: {action[0]}")
        #     print(
        #         f"Wanted change rate: {wanted_change_rate} Real change rate: {real_change_rate}")
        #     print(
        #         f"Current price: {current_price if self.current_step < len(self.price_data) else 'N/A'}")
        #     print(
        #         f"Mean price: {self.mean_price if self.current_step < len(self.price_data) else 'N/A'}")
        #     print(
        #         f"Price difference: {price_diff if self.current_step < len(self.price_data) else 'N/A'}")
        #     print(f"Reward: {reward}")

        self.current_step += 1

        return self._get_observation(), reward, done, False, {"balance": self.balance}
