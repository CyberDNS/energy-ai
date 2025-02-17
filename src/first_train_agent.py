import gymnasium as gym
import numpy as np
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from battery_env import BatteryEnv
from datetime import datetime
import os
import glob

# Define training parameters
TRAINING_STEPS = 300_000

DATA_PATH = os.getenv("DATA_PATH")
MODEL_PATH = f"{DATA_PATH}/models/battery_rl_model"
PRICE_DATA_PATH_PATTERN = f"{DATA_PATH}/fetched_data/electricity_prices_*.json"


def train():
    # Get all JSON files in the fetched_data folder
    price_data_files = glob.glob(PRICE_DATA_PATH_PATTERN)

    # Initialize a new model
    env = make_vec_env(lambda: BatteryEnv(price_data_files[0]), n_envs=1)
    model = PPO("MlpPolicy", env, verbose=1)
    print("Initialized a new model")

    # Train the model on each file sequentially
    for file in price_data_files:
        print(f"Training on file: {file}")
        env = make_vec_env(lambda: BatteryEnv(file), n_envs=1)
        model.set_env(env)
        model.learn(total_timesteps=TRAINING_STEPS)
        env.close()
        print(f"Completed training on file: {file}")

    # Save the refined model
    filename = f"{MODEL_PATH}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    model.save(filename)
    print(f"Model saved to {filename}")


if __name__ == "__main__":
    train()
