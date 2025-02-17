import os
import json
import time
import paho.mqtt.client as mqtt
from datetime import datetime
from dotenv import load_dotenv
from incremental_train_agent import train
from multiprocessing import Process
from inference_api import app
import requests

# Load environment variables from .env file
load_dotenv()

DATA_PATH = os.getenv("DATA_PATH")

# Define MQTT server details
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

# Define the path to save the fetched data
PRICE_DATA_PATH = f"{DATA_PATH}/electricity_prices.json"

# Global variable to store the fetched data
fetched_data = None


def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    global fetched_data
    fetched_data = json.loads(msg.payload.decode())

    # Archive old data with a date
    if os.path.exists(PRICE_DATA_PATH):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        archive_path = f"{PRICE_DATA_PATH}.{timestamp}.bak"
        os.rename(PRICE_DATA_PATH, archive_path)
        print(f"Old data archived to {archive_path}")

    with open(PRICE_DATA_PATH, "w") as f:
        json.dump(fetched_data, f)
    print(f"Data fetched and saved to {PRICE_DATA_PATH}")


def fetch_data():
    client = mqtt.Client(client_id="energy-ai")
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    # Wait for the data to be fetched
    while fetched_data is None:
        time.sleep(1)

    client.loop_stop()
    client.disconnect()


def start_web_server():
    app.run(host="0.0.0.0", port=5000)


def reload_model():
    response = requests.post("http://localhost:5000/reload_model")
    if response.status_code == 200:
        print("Model reloaded successfully")
    else:
        print("Failed to reload model")


def main():
    # Start the web server in a separate process
    web_server_process = Process(target=start_web_server)
    web_server_process.start()

    while True:
        now = datetime.now()
        # datetime now from germany
        now = now.astimezone()

        fetch_data()
        if now.hour == 14:
            train()
            reload_model()  # Call the reload_model function after training

        time.sleep(3600)  # Sleep for an hour


if __name__ == "__main__":
    main()
