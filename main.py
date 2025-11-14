from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List
from datetime import datetime
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from grafana_proxy import router as grafana_router

# 알람 시스템 import
from alert_engine import AlertEngine
from llm_client import LLMClient
from notifier import SlackNotifier, EmailNotifier

load_dotenv()

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")

influx_client: InfluxDBClient | None = None
write_api = None

# 알람 시스템 전역 변수
alert_engine: AlertEngine | None = None
llm_client: LLMClient | None = None
slack_notifier: SlackNotifier | None = None
email_notifier: EmailNotifier | None = None

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="IoT Sensor API")

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

# Grafana proxy router (exposes /grafana/* -> proxied to configured Grafana)
app.include_router(grafana_router)

mqtt_client = mqtt.Client()
latest_sensor_data: dict = {}
event_loop: asyncio.AbstractEventLoop | None = None


def on_connect(client, userdata, flags, rc):  # pylint: disable=unused-argument
    logging.info("MQTT Connected with result code %s", rc)
    client.subscribe("sensors/vibration")


def on_message(client, userdata, msg):  # pylint: disable=unused-argument
    global latest_sensor_data  # noqa: PLW0603
    global write_api  # noqa: PLW0602

    try:
        payload = json.loads(msg.payload.decode())
        latest_sensor_data = payload
        logging.info("Received sensor data: %s", payload)

        if write_api:
            vibration = payload.get("vibration", {})
            point = (
                Point("sensor_reading")
                .tag("device_id", payload.get("device_id", "unknown"))
                .tag("sensor_type", payload.get("sensor_type", "unknown"))
                .field("vibration_x", float(vibration.get("x", 0.0)))
                .field("vibration_y", float(vibration.get("y", 0.0)))
                .field("vibration_z", float(vibration.get("z", 0.0)))
                .field("vibration_magnitude", float(vibration.get("magnitude", 0.0)))
                .field("temperature", float(payload.get("temperature", 0.0)))
                .field("rpm", float(payload.get("rpm", 0.0)))
                .time(payload.get("timestamp"), WritePrecision.NS)
            )
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

        if event_loop and not event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(manager.broadcast(payload), event_loop)
        else:
            logging.warning("Event loop not ready. Skipping broadcast.")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Error processing MQTT message: %s", exc)


mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


@app.on_event("startup")
async def startup_event() -> None:
    global event_loop  # noqa: PLW0603
    global influx_client  # noqa: PLW0603
    global write_api  # noqa: PLW0603
    global alert_engine, llm_client, slack_notifier, email_notifier

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
            slack_notifier = SlackNotifier()
            email_notifier = EmailNotifier()
            
            # 알람 워커 시작
            asyncio.create_task(alert_worker())
            logging.info("✅ Alert system initialized")
        else:
            logging.warning("InfluxDB environment variables missing. Skipping InfluxDB init.")

        mqtt_client.connect("localhost", 1883, 60)
        mqtt_client.loop_start()
        logging.info("MQTT client started")
    except Exception as exc:  # pylint: disable=broad-except
        logging.error("Failed to connect to MQTT broker: %s", exc)


# ==================== 알람 시스템 ====================

async def alert_worker():
    """5초마다 알람 조건 체크"""
    # 실제 센서 ID로 변경하세요
    sensor_ids = ["sensor_001", "sensor_002", "sensor_003"]
    
    logging.info(f"🔍 Alert worker started. Monitoring sensors: {sensor_ids}")
    
    while True:
        try:
            if not alert_engine:
                logging.warning("Alert engine not initialized. Skipping check.")
                await asyncio.sleep(5)
                continue
                
            for sensor_id in sensor_ids:
                # 온도 체크
                temp_alert = await alert_engine.check_temperature_critical(sensor_id)
                if temp_alert:
                    await handle_alert(temp_alert)
                
                # 진동 체크
                vib_alert = await alert_engine.check_vibration_sustained(sensor_id)
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
        
        # Slack 전송
        if slack_notifier:
            await slack_notifier.send(alert)
        
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


# ================== API 엔드포인트 ====================
# ==================== API 엔드포인트 ====================

@app.post("/api/debug/test-alert")
async def debug_test_alert():
    """
    프론트–백엔드 연동 확인용 디버그 알람 한 번 쏘는 엔드포인트
    실제 AlertEngine 흐름과 비슷한 형식으로 alert dict를 만든다.
    """
    alert = {
        "id": f"debug-{datetime.utcnow().isoformat()}",
        "level": "warning",
        "message": "디버그용 테스트 알람입니다.",
        "llm_summary": None,
        "sensor_id": "debug_sensor",
        "source": "debug-api",
        "ts": datetime.utcnow().isoformat(),
    }

    # 옵션: LLM 요약도 한번 붙여보고 싶으면
    if llm_client:
        try:
            summary = await llm_client.generate_alert_summary(alert)
            if summary:
                alert["llm_summary"] = summary
        except Exception as e:
            logging.error("LLM summary error in debug_test_alert: %s", e)

    # WebSocket으로 프론트에 브로드캐스트
    await manager.broadcast({
        "type": "alert",
        "payload": alert,
    })

    logging.info("✅ Sent debug alert: %s", alert["id"])
    return {"status": "ok", "alert": alert}

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