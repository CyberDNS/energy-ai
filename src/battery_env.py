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
        forecast_horizon=24,
        episode_length=24,
        battery_cost=600,
        cycle_life=6000,
    ):
        super(BatteryEnv, self).__init__()

        self.price_data = pd.read_json(price_data_path)[
            "data"]  # Load JSON price data
        self.max_data_points = 48
        self.forecast_horizon = forecast_horizon
        self.episode_length = episode_length
        self.max_change_rate = max_change_rate
        self.current_step = 0
        self.inference_mode = inference_mode
        self.start_soc = start_soc
        self.start_step = start_step

        self.battery_cost = battery_cost
        self.cycle_life = cycle_life
        self.cost_per_cycle = battery_cost / cycle_life

        self.penalty_factor = 1.5

        # Calculate mean price for the complete data
        self.mean_price = np.mean(
            [
                float(self.price_data[i]["adjustedPrice"])
                for i in range(0, len(self.price_data))
            ]
        )

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
            self.current_step = np.random.randint(0, len(self.price_data) - 1)
            self.soc = np.random.uniform(0.2, 0.8)  # Random initial SoC
            self.max_change_rate = np.random.uniform(0.1, 0.5)
        else:
            self.current_step = self.start_step
            self.soc = self.start_soc

        return self._get_observation(), {}

    def _get_observation(self):
        """Return the current observation state."""
        all_prices = [
            (
                self.normalize_price(
                    float(self.price_data[i]["adjustedPrice"]))
                if i < len(self.price_data)
                else self.normalize_price(self.mean_price)
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
        if self.max_price == self.min_price:
            return 0.5
        if price <= self.mean_price:
            return 0.5 * (price - self.min_price) / (self.mean_price - self.min_price)
        else:
            return 0.5 + 0.5 * (price - self.mean_price) / (self.max_price - self.mean_price)

    def step(self, action):
        """Apply the agent's action and calculate the reward."""

        # Ensure the episode lasts exactly 48 steps
        done = self.current_step >= self.max_data_points - 1
        reward = 0.0

        wanted_change_rate = action[0] * self.max_change_rate

        real_change_rate = wanted_change_rate
        if self.soc + wanted_change_rate > 1:
            real_change_rate = 1 - self.soc
        elif self.soc + wanted_change_rate < 0:
            real_change_rate = -self.soc

        if self.current_step < len(self.price_data):
            current_price = self.normalize_price(float(
                self.price_data[self.current_step]["adjustedPrice"]))

            price_diff = current_price - 0.5

            if self.current_step == 17:
                debug_stop = 0

            if price_diff > 0:  # High price period
                if wanted_change_rate < 0:  # Discharge is wanted
                    reward += (
                        price_diff * -1 * real_change_rate
                    )  # Reward for real discharging
                    if real_change_rate > wanted_change_rate:
                        # Penalty for not discharging enough
                        reward += self.penalty_factor * (
                            price_diff * (wanted_change_rate -
                                          real_change_rate)
                        )
                else:  # Charge is wanted then penalize
                    reward -= self.penalty_factor * \
                        (price_diff * wanted_change_rate)
            else:  # Low price period
                if wanted_change_rate > 0:  # Charge is wanted
                    reward += (
                        -1 * price_diff * real_change_rate
                    )  # Reward for real charging
                    if (
                        real_change_rate > wanted_change_rate
                    ):  # Penalty for not charging enough
                        reward += self.penalty_factor * (
                            price_diff * (real_change_rate -
                                          wanted_change_rate)
                        )
                else:  # Discharge is wanted then penalize
                    reward += self.penalty_factor * (
                        price_diff * -1 * wanted_change_rate
                    )

        else:
            # No value available, reward is 0
            reward = 0.0

        self.soc += real_change_rate
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

        return self._get_observation(), reward, done, False, {}
