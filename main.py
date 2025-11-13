from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import List

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# 알람 시스템 import
from alert_engine import AlertEngine
from llm_client import LLMClient
from notifier import EmailNotifier

load_dotenv()

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")

# MQTT 설정
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")  # 라즈베리파이 IP 주소
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

influx_client: InfluxDBClient | None = None
write_api = None

# 알람 시스템 전역 변수
alert_engine: AlertEngine | None = None
llm_client: LLMClient | None = None
email_notifier: EmailNotifier | None = None

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan event handler for startup and shutdown"""
    global event_loop  # noqa: PLW0603
    global influx_client  # noqa: PLW0603
    global write_api  # noqa: PLW0603
    global alert_engine, llm_client, email_notifier

    # Startup
    try:
        event_loop = asyncio.get_running_loop()

        if all([INFLUX_URL, INFLUX_ORG, INFLUX_BUCKET, INFLUX_TOKEN]):
            influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            logging.info("InfluxDB client started")
            
            # 알람 시스템 초기화
            logging.info("🚀 Starting MOBY Alert System...")
            alert_engine = AlertEngine(influx_client, INFLUX_BUCKET)
            llm_client = LLMClient()
            email_notifier = EmailNotifier()
            
            # 알람 워커 시작
            asyncio.create_task(alert_worker())
            logging.info("✅ Alert system initialized")
        else:
            logging.warning("InfluxDB environment variables missing. Skipping InfluxDB init.")

        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        logging.info(f"MQTT client started (broker: {MQTT_BROKER}:{MQTT_PORT})")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed to connect to MQTT broker: %s", exc)

    yield

    # Shutdown
    try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        logging.info("MQTT client stopped")
        
        if influx_client:
            influx_client.close()
            logging.info("InfluxDB client closed")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Error during shutdown: %s", exc)


app = FastAPI(title="IoT Sensor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # 프론트엔드가 실행되는 모든 포트를 허용해야 합니다.
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logging.info("New WebSocket connection. Total: %s", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logging.info("WebSocket disconnected. Total: %s", len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        if not self.active_connections:
            return

        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as exc:  # pylint: disable=broad-except
                logging.error("Error broadcasting to WebSocket: %s", exc)
                self.disconnect(connection)


manager = ConnectionManager()

# MQTT Client v2 API 사용
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
latest_sensor_data: dict = {}
event_loop: asyncio.AbstractEventLoop | None = None


def on_connect(client, userdata, connect_flags, reason_code, properties):  # pylint: disable=unused-argument
    logging.info("MQTT Connected with reason code %s", reason_code)
    # 실제 센서 토픽 구독
    topics = [
        "factory/sensor/dht11",
        "factory/sensor/vibration",
        "factory/sensor/sound",
        "factory/sensor/accel_gyro",
        "factory/sensor/pressure",
    ]
    for topic in topics:
        client.subscribe(topic)
        logging.info(f"Subscribed to: {topic}")


def on_message(client, userdata, msg):  # pylint: disable=unused-argument
    global latest_sensor_data  # noqa: PLW0603
    global write_api  # noqa: PLW0602

    try:
        payload = json.loads(msg.payload.decode())
        sensor_type = payload.get("sensor_type", "unknown")
        fields = payload.get("fields", {})
        timestamp_ns = payload.get("timestamp_ns")
        
        logging.info(f"Received {sensor_type} data from {msg.topic}")
        
        # 토픽에서 센서 타입 추출 (백업용)
        if sensor_type == "unknown":
            topic_parts = msg.topic.split("/")
            if len(topic_parts) >= 3:
                sensor_type = topic_parts[-1]

        # InfluxDB 저장
        if write_api and timestamp_ns:
            point = Point("sensor_reading")
            point.tag("sensor_type", sensor_type)
            point.tag("sensor_model", payload.get("sensor_model", "unknown"))
            
            # 센서 타입별 필드 저장
            if sensor_type == "dht11":
                point.field("temperature_c", float(fields.get("temperature_c", 0.0)))
                point.field("humidity_percent", float(fields.get("humidity_percent", 0.0)))
                # 온도 데이터를 latest_sensor_data에도 저장 (알람용)
                latest_sensor_data = {
                    "sensor_type": sensor_type,
                    "temperature": fields.get("temperature_c", 0.0),
                    "timestamp": timestamp_ns
                }
                
            elif sensor_type == "vibration":
                point.field("vibration_raw", int(fields.get("vibration_raw", 0)))
                point.field("vibration_voltage", float(fields.get("vibration_voltage", 0.0)))
                # 진동 전압을 magnitude로 사용 (임계값 체크용)
                latest_sensor_data = {
                    "sensor_type": sensor_type,
                    "vibration_magnitude": fields.get("vibration_voltage", 0.0),
                    "timestamp": timestamp_ns
                }
                
            elif sensor_type == "sound":
                point.field("sound_raw", int(fields.get("sound_raw", 0)))
                point.field("sound_voltage", float(fields.get("sound_voltage", 0.0)))
                
            elif sensor_type == "accel_gyro":
                point.field("accel_x", float(fields.get("accel_x", 0.0)))
                point.field("accel_y", float(fields.get("accel_y", 0.0)))
                point.field("accel_z", float(fields.get("accel_z", 0.0)))
                point.field("gyro_x", float(fields.get("gyro_x", 0.0)))
                point.field("gyro_y", float(fields.get("gyro_y", 0.0)))
                point.field("gyro_z", float(fields.get("gyro_z", 0.0)))
                
            elif sensor_type == "pressure":
                point.field("temperature_c", float(fields.get("temperature_c", 0.0)))
                point.field("pressure_hpa", float(fields.get("pressure_hpa", 0.0)))
                if "altitude_m" in fields:
                    point.field("altitude_m", float(fields.get("altitude_m", 0.0)))
                if "sea_level_pressure_hpa" in fields:
                    point.field("sea_level_pressure_hpa", float(fields.get("sea_level_pressure_hpa", 0.0)))
            
            # timestamp_ns를 나노초로 변환
            point.time(int(timestamp_ns), WritePrecision.NS)
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

        # WebSocket 브로드캐스트 (원본 payload 전송)
        if event_loop and not event_loop.is_closed():
            broadcast_payload = {
                "topic": msg.topic,
                "sensor_type": sensor_type,
                **payload
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast(broadcast_payload), event_loop)
        else:
            logging.warning("Event loop not ready. Skipping broadcast.")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Error processing MQTT message: %s", exc)


mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan event handler for startup and shutdown"""
    global event_loop  # noqa: PLW0603
    global influx_client  # noqa: PLW0603
    global write_api  # noqa: PLW0603
    global alert_engine, llm_client, email_notifier

    # Startup
    try:
        event_loop = asyncio.get_running_loop()

        if all([INFLUX_URL, INFLUX_ORG, INFLUX_BUCKET, INFLUX_TOKEN]):
            influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            logging.info("InfluxDB client started")
            
            # 알람 시스템 초기화
            logging.info("🚀 Starting MOBY Alert System...")
            alert_engine = AlertEngine(influx_client, INFLUX_BUCKET)
            llm_client = LLMClient()
            email_notifier = EmailNotifier()
            
            # 알람 워커 시작
            asyncio.create_task(alert_worker())
            logging.info("✅ Alert system initialized")
        else:
            logging.warning("InfluxDB environment variables missing. Skipping InfluxDB init.")

        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        logging.info(f"MQTT client started (broker: {MQTT_BROKER}:{MQTT_PORT})")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed to connect to MQTT broker: %s", exc)

    yield

    # Shutdown
    try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        logging.info("MQTT client stopped")
        
        if influx_client:
            influx_client.close()
            logging.info("InfluxDB client closed")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Error during shutdown: %s", exc)


app = FastAPI(title="IoT Sensor API", lifespan=lifespan)


# ==================== 알람 시스템 ====================

async def alert_worker():
    """5초마다 알람 조건 체크"""
    # 센서 타입별 모니터링 (device_id 대신 sensor_type 사용)
    sensor_types = ["pressure", "vibration"]  # 온도는 BMP180(pressure), 진동은 vibration
    
    logging.info(f"🔍 Alert worker started. Monitoring sensor types: {sensor_types}")
    
    while True:
        try:
            if not alert_engine:
                logging.warning("Alert engine not initialized. Skipping check.")
                await asyncio.sleep(5)
                continue
                
            # 온도 체크 (BMP180 pressure 센서)
            if "pressure" in sensor_types:
                temp_alert = await alert_engine.check_temperature_critical("pressure")
                if temp_alert:
                    await handle_alert(temp_alert)
            
            # 진동 체크 (vibration 센서)
            if "vibration" in sensor_types:
                vib_alert = await alert_engine.check_vibration_sustained("vibration")
                if vib_alert:
                    await handle_alert(vib_alert)
            
            await asyncio.sleep(5)  # 5초 간격
        except Exception as e:
            logging.error(f"Alert worker error: {e}")
            await asyncio.sleep(5)


async def handle_alert(alert: dict):
    """알람 발생 시 처리"""
    try:
        # LLM 요약 생성 (있으면)
        if llm_client:
            llm_summary = await llm_client.generate_alert_summary(alert)
            if llm_summary:
                alert["llm_summary"] = llm_summary
        
        # Email 전송 (Critical만)
        if email_notifier:
            await email_notifier.send(alert)
        
        # WebSocket으로 프론트엔드에 브로드캐스트
        await manager.broadcast({
            "type": "alert",
            "payload": alert
        })
        
        logging.info(f"✅ Alert handled: {alert['id']}")
    except Exception as e:
        logging.error(f"Alert handling error: {e}")


# ==================== API 엔드포인트 ====================

@app.get("/api/alerts/history")
async def get_alert_history(hours: int = 24):
    """최근 알람 히스토리 조회"""
    if not alert_engine:
        return {"alerts": [], "error": "Alert engine not initialized"}
    
    return {
        "alerts": alert_engine.get_alert_history(hours)
    }


#@app.websocket("/ws")
@app.websocket("/ws/sensor")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 연결"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logging.info(f"Received from client: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)