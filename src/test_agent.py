import os
import gymnasium as gym
import numpy as np
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from battery_env import BatteryEnv  # Import custom environment
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load trained model
DATA_PATH = os.getenv("DATA_PATH")
MODEL_PATH = f"{DATA_PATH}/models/battery_rl_model_20250216142256"
PRICE_DATA_PATH = f"{DATA_PATH}/fetched_data/electricity_prices_20250213.json"

model = PPO.load(MODEL_PATH)

# Create the environment

start_step = 0

env = BatteryEnv(
    PRICE_DATA_PATH,
    inference_mode=True,
    start_soc=0.1,
    start_step=start_step,
    max_change_rate=0.16,
)
obs, _ = env.reset()

# Storage for visualization
soc_values = []
action_values = []
reward_values = []
adjusted_prices = []

# Run a single episode

current_step = start_step

done = False
while not done:

    action, _states = model.predict(obs, deterministic=True)
    obs, reward, done, _, _ = env.step(action)

    soc_values.append(obs[0])  # Store state of charge
    action_values.append(action[0])  # Store actions taken
    reward_values.append(reward)  # Store rewards
    # Store adjusted price (first element after SoC)
    adjusted_prices.append(obs[3 + current_step])
    # Log the current step
    print(
        f"Step {current_step}: SOC={obs[0]:.2f}, Action={action[0]:.2f}, Reward={reward:.2f}"
    )
    current_step += 1

# Plot battery SoC over time
plt.figure(figsize=(12, 12))
plt.subplot(4, 1, 1)
plt.plot(soc_values, label="State of Charge (SoC)")
plt.ylabel("SoC (0-1)")
plt.legend()
plt.xticks(ticks=np.arange(0, len(soc_values)),
           labels=np.arange(0, len(soc_values)))

# Plot agent's actions over time
plt.subplot(4, 1, 2)
plt.plot(action_values, label="Agent's Action", color="orange")
plt.ylabel("Action (-1=Discharge, 1=Charge)")
plt.legend()
plt.xticks(
    ticks=np.arange(0, len(action_values)), labels=np.arange(0, len(action_values))
)

# Plot reward progression
plt.subplot(4, 1, 3)
plt.plot(reward_values, label="Rewards", color="green")
plt.ylabel("Reward")
plt.legend()
plt.xticks(
    ticks=np.arange(0, len(reward_values)), labels=np.arange(0, len(reward_values))
)

# Plot adjusted prices over time
plt.subplot(4, 1, 4)
plt.plot(adjusted_prices, label="Adjusted Prices", color="blue")
plt.ylabel("Price")
plt.xlabel("Time Steps")
plt.legend()
plt.xticks(
    ticks=np.arange(0, len(adjusted_prices)), labels=np.arange(0, len(adjusted_prices))
)

plt.show()

env.close()
