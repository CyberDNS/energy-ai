import os
import json
import glob
import paho.mqtt.client as mqtt
from flask import Flask, request, jsonify
from stable_baselines3 import PPO
from battery_env import BatteryEnv  # Import custom environment
from datetime import datetime

app = Flask(__name__)

# Load the trained model
DATA_PATH = os.getenv("DATA_PATH")

MODEL_PATH = f"{DATA_PATH}/models/battery_rl_model_v0_3"
PRICE_DATA_PATH = f"{DATA_PATH}/electricity_prices.json"
model = PPO.load(MODEL_PATH)

# Define MQTT server details
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_PUBLISH_TOPIC = os.getenv("MQTT_PUBLISH_TOPIC")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")


@app.route("/reload_model", methods=["POST"])
def reload_model():
    global model
    model = PPO.load(MODEL_PATH)
    return jsonify({"message": "Model reloaded successfully"})


@app.route("/infer_change_rate", methods=["POST"])
def infer_change_rate():
    data = request.get_json()
    if (
        not data
        or "current_soc" not in data
        or "capacity" not in data
        or "max_change_rate" not in data
        or "current_step" not in data
    ):
        return jsonify({"error": "Invalid input"}), 400

    current_soc = data["current_soc"]  # Based on usable capacity
    capacity = data["capacity"]  # In Wh
    max_change_rate = data["max_change_rate"]  # In W
    max_change_rate_normalized = max_change_rate / capacity
    current_step = data["current_step"]

    # Create the environment
    env = BatteryEnv(
        PRICE_DATA_PATH,
        inference_mode=True,
        start_soc=current_soc,
        start_step=current_step,
        max_change_rate=max_change_rate_normalized,
    )
    obs, _ = env.reset()

    # predict the action
    action, _states = model.predict(obs, deterministic=True)

    env.close()

    return jsonify({"change_rate": float(action[0])})


@app.route("/publish_inference", methods=["POST"])
def publish_inference():
    data = request.get_json()
    if (
        not data
        or "current_soc" not in data
        or "capacity" not in data
        or "max_change_rate" not in data
        or "current_step" not in data
    ):
        return jsonify({"error": "Invalid input"}), 400

    current_soc = data["current_soc"]
    capacity = data["capacity"]
    max_change_rate = data["max_change_rate"]
    max_change_rate_normalized = max_change_rate / capacity
    current_step = data["current_step"]

    # Load price data
    with open(PRICE_DATA_PATH, "r") as f:
        price_data = json.load(f)

    # Create the environment
    env = BatteryEnv(
        PRICE_DATA_PATH,
        inference_mode=True,
        start_soc=current_soc,
        start_step=current_step,
        max_change_rate=max_change_rate_normalized,
    )
    obs, _ = env.reset()

    inference_results = []

    for i in range(current_step, len(price_data["data"])):
        action, _states = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)

        # Get the hour and date from the price data
        price_entry = price_data["data"][i]
        hour = price_entry["hour"]
        date = price_entry["date"]

        result = {
            "index": i,
            "hour": hour,
            "date": date,
            "changeRate": f"{action[0]:.2f}"
        }
        inference_results.append(result)

    payload = json.dumps({"data": inference_results})

    # Publish to MQTT
    client = mqtt.Client(client_id="energy-ai")
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.publish(MQTT_PUBLISH_TOPIC, payload, retain=True)
    client.disconnect()

    env.close()

    return jsonify({"message": "Inference results published to MQTT"})


@app.route("/get_historical_data", methods=["GET"])
def get_historical_data():
    try:
        # Get all JSON files including backups
        files = glob.glob(f"{DATA_PATH}/electricity_prices*")

        all_data = {}
        i = 0
        for file in files:
            with open(file, "r") as f:
                historical_data = json.load(f)
                key = f'electricity_prices_{datetime.strptime(historical_data["data"][0]["date"], "%Y-%m-%d").strftime("%Y%m%d")}_{i}'
                i += 1
                all_data[key] = historical_data["data"]

        return jsonify(all_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
