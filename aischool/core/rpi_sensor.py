#!/usr/bin/env python3
"""
Raspberry Pi 4 vibration monitoring demo script.
"""

import json
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt


# MQTT broker configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "sensors/vibration"


# Create MQTT client and establish connection
client = mqtt.Client(client_id="raspberry-pi-sensor")
client.connect(MQTT_BROKER, MQTT_PORT, 60)


def generate_sensor_data():
    """Generate random sensor data for demo purposes."""

    # Vibration data (m/s^2)
    vibration_x = round(random.uniform(0.1, 2.5), 2)
    vibration_y = round(random.uniform(0.1, 2.5), 2)
    vibration_z = round(random.uniform(0.1, 2.5), 2)

    # Temperature (degC)
    temperature = 45.0
    # RPM data
    rpm = random.randint(1500, 3000)

    # Compose payload
    sensor_data = {
        "timestamp": datetime.now().isoformat(),
        "vibration": {
            "x": vibration_x,
            "y": vibration_y,
            "z": vibration_z,
            "magnitude": round((vibration_x**2 + vibration_y**2 + vibration_z**2) ** 0.5, 2),
        },
        "temperature": temperature,
        "rpm": rpm,
        "device_id": "raspberry-pi-4",
        "sensor_type": "vibration",
    }

    return sensor_data


def publish_sensor_data():
    """Publish generated sensor data to the configured MQTT broker."""

    try:
        data = generate_sensor_data()
        payload = json.dumps(data, ensure_ascii=False)

        result = client.publish(MQTT_TOPIC, payload, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[{data['timestamp']}] Sensor payload published")
        else:
            print(f"!! MQTT publish failed: {result.rc}")

    except Exception as exc:  # pylint: disable=broad-except
        print(f"Unexpected error: {exc}")


def main():
    """Entry point."""

    print("=" * 50)
    print("Raspberry Pi sensor telemetry simulation")
    print("=" * 50)
    print(f"MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"Topic: {MQTT_TOPIC}")
    print("Publish interval: 5 seconds")
    print("=" * 50)
    print()

    try:
        client.loop_start()  # Start MQTT network loop in a separate thread

        while True:
            publish_sensor_data()
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping...")
        client.loop_stop()
        client.disconnect()
        print("MQTT connection closed.")


if __name__ == "__main__":
    main()
