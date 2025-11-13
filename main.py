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
from moby_backend.core.alert_engine import AlertEngine
from moby_backend.core.llm_client import LLMClient
from moby_backend.core.notifier import EmailNotifier

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
            # start weekly report scheduler
            asyncio.create_task(weekly_report_scheduler())
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


async def generate_timeseries_summary(hours: int = 168, sensor_types: list | None = None) -> dict:
    """Aggregate InfluxDB metrics for the given period (hours). Returns summary dict."""
    if not influx_client:
        return {"metrics": {}}

    query_api = influx_client.query_api()
    summary = {"start": f"-{hours}h", "end": "now", "metrics": {}}

    sensor_fields = {
        "dht11": ["temperature_c", "humidity_percent"],
        "vibration": ["vibration_voltage"],
        "sound": ["sound_voltage"],
        "accel_gyro": ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"],
        "pressure": ["temperature_c", "pressure_hpa", "altitude_m", "sea_level_pressure_hpa"],
    }

    requested = sensor_types or list(sensor_fields.keys())

    def run_scalar_query(flux: str):
        try:
            res = query_api.query(flux)
            for table in res:
                for record in table.records:
                    return record.get_value()
        except Exception as e:
            logging.error("Influx query error: %s", e)
        return None

    for sensor in requested:
        fields = sensor_fields.get(sensor, [])
        if not fields:
            continue
        summary["metrics"][sensor] = {}
        for field in fields:
            stats = {"mean": None, "min": None, "max": None}
            flux_mean = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r["_measurement"] == "sensor_reading")
  |> filter(fn: (r) => r["sensor_type"] == "{sensor}")
  |> filter(fn: (r) => r["_field"] == "{field}")
  |> mean()
'''
            m = run_scalar_query(flux_mean)
            stats["mean"] = float(m) if m is not None else None

            flux_min = flux_mean.replace("mean()", "min()")
            mi = run_scalar_query(flux_min)
            stats["min"] = float(mi) if mi is not None else None

            flux_max = flux_mean.replace("mean()", "max()")
            ma = run_scalar_query(flux_max)
            stats["max"] = float(ma) if ma is not None else None

            summary["metrics"][sensor][field] = stats

    return summary


async def generate_and_store_weekly_report():
    """Create weekly summary and generate LLM report (no DB storage)."""
    try:
        summary = await generate_timeseries_summary(hours=24 * 7)
        report_text = ""
        if llm_client:
            report_text = await llm_client.generate_timeseries_report(summary)

        # create a report record-like dict
        report_record = {
            "id": f"weekly_{int(__import__('time').time())}",
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "sensor_id": "aggregate",
            "level": "INFO",
            "metric": "weekly_summary",
            "value": None,
            "threshold": None,
            "raw_summary": summary,
            "llm_summary": report_text,
        }

        # PostgreSQL storage of reports has been removed per configuration.

        logging.info("Weekly report generated and stored")
    except Exception as e:
        logging.error(f"Failed to generate/store weekly report: {e}")


def seconds_until_next(day_of_week: int = 0, hour: int = 0, minute: int = 0, tz_name: str = "UTC") -> int:
    """Return seconds until next given weekday/time in the given timezone.

    day_of_week: Monday=0..Sunday=6
    tz_name: IANA timezone name (e.g. 'Asia/Seoul'). Falls back to UTC arithmetic if zoneinfo unavailable.
    """
    from datetime import datetime, timedelta, timezone

    try:
        # Prefer the stdlib ZoneInfo (Python 3.9+)
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)

        days_ahead = (day_of_week - now.weekday() + 7) % 7
        target_date = (now.date() + timedelta(days=days_ahead))
        target = datetime(year=target_date.year, month=target_date.month, day=target_date.day,
                          hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz)
        if target <= now:
            target += timedelta(days=7)

        # compute seconds until target relative to UTC now to avoid clock skew
        now_utc = datetime.now(timezone.utc)
        delta = target.astimezone(timezone.utc) - now_utc
        return int(delta.total_seconds())
    except Exception:
        # fallback: approximate using UTC offset heuristic (Asia/Seoul -> +9)
        from datetime import datetime as _dt

        offset_hours = 9 if ("Seoul" in tz_name or "KST" in tz_name) else 0
        now_local = _dt.utcnow() + timedelta(hours=offset_hours)
        days_ahead = (day_of_week - now_local.weekday() + 7) % 7
        target = _dt(year=now_local.year, month=now_local.month, day=now_local.day) + timedelta(days=days_ahead)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_local:
            target += timedelta(days=7)
        delta = target - now_local
        return int(delta.total_seconds())


async def weekly_report_scheduler():
    """Schedule weekly report generation. Default: Monday 09:00 KST (Asia/Seoul)."""
    try:
        # compute initial delay (KST Monday 09:00)
        delay = seconds_until_next(day_of_week=0, hour=9, minute=0, tz_name="Asia/Seoul")
        logging.info(f"Weekly report scheduler sleeping for {delay} seconds until next run (KST Mon 09:00)")
        await asyncio.sleep(delay)
        while True:
            await generate_and_store_weekly_report()
            # sleep for 7 days
            await asyncio.sleep(7 * 24 * 3600)
    except asyncio.CancelledError:
        logging.info("Weekly report scheduler cancelled")
    except Exception as e:
        logging.error(f"weekly_report_scheduler error: {e}")