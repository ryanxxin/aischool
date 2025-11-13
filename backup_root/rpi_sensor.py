'''
Backup of root-level rpi_sensor.py
'''
#!/usr/bin/env python3
import json
import random
import time
from datetime import datetime
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "sensors/vibration"

client = mqtt.Client(client_id="raspberry-pi-sensor")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

def generate_sensor_data():
    vibration_x = round(random.uniform(0.1, 2.5), 2)
    vibration_y = round(random.uniform(0.1, 2.5), 2)
    vibration_z = round(random.uniform(0.1, 2.5), 2)
    temperature = 45.0
    rpm = random.randint(1500, 3000)
    sensor_data = {
        "timestamp": datetime.now().isoformat(),
        "vibration": {"x": vibration_x, "y": vibration_y, "z": vibration_z, "magnitude": round((vibration_x**2 + vibration_y**2 + vibration_z**2) ** 0.5, 2)},
        "temperature": temperature,
        "rpm": rpm,
        "device_id": "raspberry-pi-4",
        "sensor_type": "vibration",
    }
    return sensor_data

def publish_sensor_data():
    try:
        data = generate_sensor_data()
        payload = json.dumps(data, ensure_ascii=False)
        result = client.publish(MQTT_TOPIC, payload, qos=1)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
