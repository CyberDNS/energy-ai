# app.py
import os
import json
import time
import threading
import logging
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from linear_optimizer import run_optimization

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,  # Set default logging level to INFO
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to stdout for Docker compatibility
    ]
)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()

# --- Configuration ---
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC_SCHEDULE = os.getenv("MQTT_TOPIC", "battery/schedule/optimal")
MQTT_TOPIC_FORECAST = os.environ.get(
    "MQTT_TOPIC_FORECAST", "iobroker/userdata/0/tibber-adjusted-prices")
MQTT_TIMEOUT_SECONDS = 5

MQTT_AUTH = None
if MQTT_USERNAME:
    MQTT_AUTH = {'username': MQTT_USERNAME, 'password': MQTT_PASSWORD}
    logger.info("MQTT Authentication: Enabled")
else:
    logger.info("MQTT Authentication: Disabled (no username specified)")

DEFAULT_BATTERY_PARAMS = {
    'capacity_kwh': 7.4,
    'max_rate_kw': 0.8,
    'min_soc_percent': 10,
    'efficiency_roundtrip': 0.90
}

# --- Flask App ---
app = Flask(__name__)

# --- MQTT Forecast Fetching (with Auth) ---


def fetch_latest_forecast_from_mqtt(broker, port, topic, timeout, username, password):
    logger.info(
        f"Attempting to fetch forecast from MQTT: {broker}:{port} Topic: {topic}")
    received_event = threading.Event()
    message_payload = None

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info(
                f"MQTT connected successfully, subscribing to {topic}...")
            client.subscribe(topic)
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            received_event.set()

    def on_message(client, userdata, msg):
        nonlocal message_payload
        logger.info(f"Received forecast message on {msg.topic}")
        try:
            message_payload = msg.payload.decode('utf-8')
            if '"data":' not in message_payload:
                logger.warning(
                    "Received payload doesn't seem to contain 'data' key.")
                message_payload = None
        except Exception as e:
            logger.error(f"Error decoding MQTT message payload: {e}")
            message_payload = None
        finally:
            received_event.set()

    client_id = f"flask-optimizer-fetcher-{os.getpid()}"
    client = mqtt.Client(client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message

    if username:
        client.username_pw_set(username, password)
        logger.info("MQTT Fetch Client: Using username/password.")

    try:
        client.connect(broker, port, 60)
        client.loop_start()

        logger.info(f"Waiting for forecast message (max {timeout} seconds)...")
        event_triggered = received_event.wait(timeout=timeout)

        client.loop_stop()
        client.disconnect()
        logger.info("MQTT fetch client disconnected.")

        if event_triggered and message_payload:
            logger.info("Forecast data fetched successfully.")
            return message_payload
        elif event_triggered and not message_payload:
            logger.error(
                "Connection/Message processing error occurred during fetch.")
            return None
        else:
            logger.error(
                f"Timeout - No forecast message received on {topic} within {timeout}s.")
            return None

    except Exception as e:
        logger.error(f"MQTT fetch connection or operation failed: {e}")
        if client.is_connected():
            try:
                client.loop_stop(force=True)
                client.disconnect()
            except:
                pass
        return None

# --- API Endpoint ---


@app.route('/optimize', methods=['POST'])
def optimize_endpoint():
    logger.info("Received request on /optimize (using MQTT forecast, with auth)")

    if not request.is_json:
        logger.debug("Request content type is not JSON.")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    logger.debug(f"Request JSON payload: {data}")

    forecast_json_string = fetch_latest_forecast_from_mqtt(
        MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_FORECAST, MQTT_TIMEOUT_SECONDS,
        MQTT_USERNAME, MQTT_PASSWORD
    )

    if not forecast_json_string:
        logger.error(
            f"Failed to fetch forecast data from MQTT topic {MQTT_TOPIC_FORECAST}")
        return jsonify({"error": f"Failed to fetch forecast data from MQTT topic {MQTT_TOPIC_FORECAST}"}), 503

    initial_soc = data.get('current_soc_percent')
    current_index = data.get('current_time_index')

    if initial_soc is None or current_index is None:
        logger.error(
            "Missing required fields: current_soc_percent, current_time_index")
        return jsonify({"error": "Missing required fields: current_soc_percent, current_time_index"}), 400

    battery_params = data.get('battery_params', DEFAULT_BATTERY_PARAMS)
    logger.debug(f"Battery parameters: {battery_params}")

    try:
        status, results_df, action_now, total_savings = run_optimization(
            forecast_json_string, initial_soc, current_index, battery_params
        )
        logger.debug(
            f"Optimization results: status={status}, action_now={action_now}, total_savings={total_savings}")
    except Exception as e:
        logger.error(f"Error during optimization call: {e}")
        return jsonify({"error": f"Internal optimization error: {e}"}), 500

    response = {
        "solver_status": status,
        "action_next_hour": action_now,
        "estimated_total_savings": total_savings
    }

    if status == 'Optimal' and results_df is not None:
        mqtt_payload = format_for_mqtt(results_df)
        if mqtt_payload:
            try:
                logger.info(
                    f"Publishing schedule to MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}, Topic: {MQTT_TOPIC_SCHEDULE}")
                logger.debug(f"MQTT payload: {mqtt_payload}")
                publish.single(
                    MQTT_TOPIC_SCHEDULE,
                    payload=mqtt_payload,
                    hostname=MQTT_BROKER,
                    port=MQTT_PORT,
                    auth=MQTT_AUTH
                )
                logger.info("MQTT schedule publish successful.")
                response["mqtt_publish_status"] = "Success"
            except Exception as e:
                logger.error(f"Error publishing schedule to MQTT: {e}")
                response["mqtt_publish_status"] = f"Failed: {e}"
        else:
            logger.error("Failed to format results for MQTT publishing.")
            response["mqtt_publish_status"] = "Failed: Formatting error"

        return jsonify(response), 200
    else:
        logger.warning(f"No optimal plan found. Solver status: {status}")
        response["mqtt_publish_status"] = "Skipped: No optimal plan"
        return jsonify(response), 500


def format_for_mqtt(results_df):
    if results_df is None:
        logger.debug("Results DataFrame is None. Cannot format for MQTT.")
        return None
    output_data = []
    required_cols = ["Index", "Hour", "Date", "ChangeRate"]
    if not all(col in results_df.columns for col in required_cols):
        logger.error(
            "Results DataFrame missing required columns for MQTT formatting.")
        return None
    try:
        for _, row in results_df.iterrows():
            output_data.append({
                "index": int(row["Index"]),
                "hour": int(row["Hour"]),
                "date": row["Date"],
                "changeRate": row["ChangeRate"]
            })
        logger.debug(f"Formatted MQTT payload: {output_data}")
        return json.dumps({"data": output_data})
    except Exception as e:
        logger.error(f"Error during MQTT formatting: {e}")
        return None


# --- Main Execution ---
if __name__ == '__main__':
    logger.info("Starting Flask server...")
    logger.info(f" - Schedule MQTT Topic: {MQTT_TOPIC_SCHEDULE}")
    logger.info(f" - Forecast MQTT Topic: {MQTT_TOPIC_FORECAST}")
    logger.info(f" - MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    if MQTT_USERNAME:
        logger.info(f" - MQTT User: {MQTT_USERNAME}")
    else:
        logger.info(" - MQTT User: None (Authentication Disabled)")

    app.run(debug=True, host='0.0.0.0', port=5001)
