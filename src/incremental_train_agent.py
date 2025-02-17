import gymnasium as gym
import numpy as np
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from battery_env import BatteryEnv
import os

# Define training parameters
TRAINING_STEPS = 100_000

DATA_PATH = os.getenv("DATA_PATH")
MODEL_PATH = f"{DATA_PATH}/models/battery_rl_model_v0_3"
PRICE_DATA_PATH = f"{DATA_PATH}/electricity_prices.json"


def train():
    # Check if the model already exists
    if os.path.exists(MODEL_PATH):
        # Load the existing model
        model = PPO.load(MODEL_PATH)
        print(f"Loaded existing model from {MODEL_PATH}")
    else:
        # Initialize a new model
        env = make_vec_env(lambda: BatteryEnv(PRICE_DATA_PATH), n_envs=1)
        model = PPO("MlpPolicy", env, verbose=1)
        print("Initialized a new model")

    # Update the environment with new data
    env = make_vec_env(lambda: BatteryEnv(PRICE_DATA_PATH), n_envs=1)

    # Continue training the model
    print("Starting training...")
    model.set_env(env)
    model.learn(total_timesteps=TRAINING_STEPS)
    print("Training completed!")

    # Save the refined model
    model.save(MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    # Close the environment
    env.close()


if __name__ == "__main__":
    train()
