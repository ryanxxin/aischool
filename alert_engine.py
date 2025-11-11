# backend/alert_engine.py
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import asyncio
from influxdb_client import InfluxDBClient
import os
import logging

logger = logging.getLogger(__name__)

class AlertEngine:
    SAMPLES_PER_SECOND = 1
    
    def __init__(self, influx_client: InfluxDBClient, bucket: str):
        self.client = influx_client
        self.bucket = bucket
        self.alert_state: Dict[str, datetime] = {}
        self.alert_history: List[dict] = []
        
    async def check_temperature_critical(self, sensor_id: str) -> Optional[dict]:
        threshold = float(os.getenv("TEMP_CRITICAL_THRESHOLD", 50))
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -1m)
          |> filter(fn: (r) => r["_measurement"] == "sensor_reading")
          |> filter(fn: (r) => r["device_id"] == "{sensor_id}")
          |> filter(fn: (r) => r["_field"] == "temperature")
          |> last()
        '''
        try:
            result = self.client.query_api().query(query)
            for table in result:
                for record in table.records:
                    temp = record.get_value()
                    timestamp = record.get_time()
                    if temp > threshold:
                        alert_key = f"temp_critical_{sensor_id}"
                        if self._can_send_alert(alert_key, cooldown_minutes=10):
                            alert = {
                                "id": f"{alert_key}_{int(timestamp.timestamp())}",
                                "timestamp": timestamp.isoformat(),
                                "level": "CRITICAL",
                                "sensor_id": sensor_id,
                                "metric": "temperature",
                                "value": round(temp, 2),
                                "threshold": threshold,
                                "message": f"🚨 센서 {sensor_id} 온도 임계값 초과! {temp:.1f}°C (기준: {threshold}°C)"
                            }
                            self._save_alert_history(alert)
                            logger.warning(f"ALERT: {alert['message']}")
                            return alert
        except Exception as e:
            logger.error(f"Temperature check failed for {sensor_id}: {e}")
        return None
    
    async def check_vibration_sustained(self, sensor_id: str) -> Optional[dict]:
        threshold = float(os.getenv("VIBRATION_WARNING_THRESHOLD", 3.5))
        duration = int(os.getenv("VIBRATION_DURATION_MINUTES", 5))
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{duration}m)
          |> filter(fn: (r) => r["_measurement"] == "sensor_reading")
          |> filter(fn: (r) => r["device_id"] == "{sensor_id}")
          |> filter(fn: (r) => r["_field"] == "vibration_magnitude")
          |> filter(fn: (r) => r["_value"] > {threshold})
          |> count()
        '''
        try:
            result = self.client.query_api().query(query)
            for table in result:
                for record in table.records:
                    count = record.get_value()
                    timestamp = record.get_time()
                    expected_samples = duration * 60 * self.SAMPLES_PER_SECOND * 0.8
                    if count > expected_samples:
                        alert_key = f"vib_sustained_{sensor_id}"
                        if self._can_send_alert(alert_key, cooldown_minutes=30):
                            alert = {
                                "id": f"{alert_key}_{int(timestamp.timestamp())}",
                                "timestamp": timestamp.isoformat(),
                                "level": "WARNING",
                                "sensor_id": sensor_id,
                                "metric": "vibration",
                                "value": count,
                                "threshold": threshold,
                                "duration_minutes": duration,
                                "message": f"⚠️ 센서 {sensor_id} 진동이 {duration}분간 지속 중! (임계값: {threshold})"
                            }
                            self._save_alert_history(alert)
                            logger.warning(f"ALERT: {alert['message']}")
                            return alert
        except Exception as e:
            logger.error(f"Vibration check failed for {sensor_id}: {e}")
        return None
    
    def _can_send_alert(self, alert_key: str, cooldown_minutes: int) -> bool:
        now = datetime.now()
        last_sent = self.alert_state.get(alert_key)
        if last_sent is None:
            self.alert_state[alert_key] = now
            return True
        if now - last_sent > timedelta(minutes=cooldown_minutes):
            self.alert_state[alert_key] = now
            return True
        return False
    
    def _save_alert_history(self, alert: dict):
        self.alert_history.append(alert)
        if len(self.alert_history) > 100:
            self.alert_history.pop(0)
    
    def get_alert_history(self, hours: int = 24) -> List[dict]:
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alert_history
            if datetime.fromisoformat(alert["timestamp"]) > cutoff
        ]
