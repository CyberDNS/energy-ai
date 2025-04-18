<img src="assets/CozyPowerBear.png" alt="Energy AI Logo" width="200">

# Energy AI API

This project provides an API for optimizing battery schedules using MQTT-based forecasts and a linear optimization algorithm.

## API Usage

### Endpoint: `/optimize`

- **Method**: `POST`
- **Content-Type**: `application/json`
- **Description**: Optimizes the battery schedule based on the provided current state of charge and forecast data fetched via MQTT.

#### Request Body
```json
{
  "current_soc_percent": 50,  // Current state of charge in percentage
  "current_time_index": 12,   // Current time index (e.g., hour of the day)
  "battery_params": {         // Optional: Custom battery parameters
    "capacity_kwh": 7.4,
    "max_rate_kw": 0.8,
    "min_soc_percent": 10,
    "efficiency_roundtrip": 0.90
  }
}
```

#### Response
- **200 OK**: Optimization successful, returns the next action and estimated savings.
- **400 Bad Request**: Missing or invalid input fields.
- **503 Service Unavailable**: Failed to fetch forecast data.
- **500 Internal Server Error**: Optimization or MQTT publishing error.

Example Response:
```json
{
  "solver_status": "Optimal",
  "action_next_hour": 0.5,
  "estimated_total_savings": 12.34,
  "mqtt_publish_status": "Success"
}
```

---

## Environment Variables

The application uses the following environment variables for configuration:

| Variable               | Default Value                     | Description                                      |
|------------------------|-----------------------------------|--------------------------------------------------|
| `MQTT_BROKER`          | `localhost`                      | MQTT broker hostname or IP address.             |
| `MQTT_PORT`            | `1883`                           | MQTT broker port.                               |
| `MQTT_TOPIC_FORECAST`  | `forecast/topic`                 | MQTT topic for receiving forecast data.         |
| `MQTT_TOPIC`           | `battery/schedule/optimal`       | MQTT topic for publishing optimized schedules.  |
| `MQTT_USERNAME`        | None                             | MQTT username for authentication (optional).    |
| `MQTT_PASSWORD`        | None                             | MQTT password for authentication (optional).    |


### Example `.env` File
```env
MQTT_BROKER=192.168.1.100
MQTT_PORT=1883
MQTT_TOPIC_FORECAST=forecast/topic
MQTT_TOPIC=battery/schedule/optimal
MQTT_USERNAME=user
MQTT_PASSWORD=pass
```

---

## Building and Publishing the Docker Image

### Build the Docker Image
To build the Docker image, use the following command:
```bash
docker buildx build --platform linux/amd64 -t registry.example.com/energy-ai:latest .
```

### Push the Docker Image
To push the image to a Docker registry:
```bash
docker push registry.example.com/energy-ai:latest
```

Replace `registry.example.com` with your Docker registry URL.

---

## Running the Application

1. Ensure the required environment variables are set (e.g., via `.env` file).
2. Run the application using Docker:
   ```bash
   docker run --env-file .env -p 5001:5001 registry.example.com/energy-ai:latest
   ```
3. Access the API at `http://localhost:5001/optimize`.

---

## Logging

Logs are output to the console in the following format:
```
[Timestamp] [LogLevel] Message
```
Adjust the logging level by modifying the `logging.basicConfig` configuration in `app.py`.

---

## Integration with Smart Home Systems

This project can be integrated into smart home systems to optimize energy usage and visualize data. In my setup, I integrated the system using ioBroker, Tibber, PVForecast, and a Zendure battery. The data is processed and pushed into MQTT, which is then consumed by Home Assistant to display charts.

### Components Used:
1. **ioBroker**: For managing states and integrating with Tibber and PVForecast.
2. **Tibber**: Provides electricity price data.
3. **PVForecast**: Supplies solar production forecasts.
4. **Zendure Battery**: Used for energy storage and control.
5. **MQTT**: Acts as a communication layer for optimized schedules.
6. **Home Assistant**: Displays the data using custom charts.

### Code Disclaimer:
The provided code is heavily adapted for my specific use case. You may need to modify it to suit your own setup and requirements.

#### Relevant Files:
- `tibber-prices.js`: Processes Tibber prices and solar forecasts to calculate adjusted prices.
- `zendure-control-ai.js`: Controls the Zendure battery based on AI-optimized schedules.
- `hass-apexcharts-pricegraph.yml`: Displays Tibber prices and adjusted prices in Home Assistant.
- `hass-apexcharts-actionschart.yml`: Visualizes battery actions in Home Assistant.

---

## Example Charts in Home Assistant

### Tibber Prices Adjusted by Solar Production
The `hass-apexcharts-pricegraph.yml` file configures a chart to display Tibber prices and adjusted prices based on solar production.

<img src="assets/hass-integration-1.png" alt="Energy AI Logo" width="400">

### Battery Actions
The `hass-apexcharts-actionschart.yml` file configures a chart to show battery charge and discharge actions.

<img src="assets/hass-integration-2.png" alt="Energy AI Logo" width="400">
