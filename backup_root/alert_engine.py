// backup of root alert_engine.py
'''
This file is an exact backup of the original root-level alert_engine.py
'''

from datetime import datetime, timedelta
from typing import Dict, Optional, List
import asyncio
from influxdb_client import InfluxDBClient
import os
import logging

logger = logging.getLogger(__name__)

class AlertEngine:
    FREQ_DHT11 = 1.0
    FREQ_VIBRATION = 16.0
    def __init__(self, influx_client: InfluxDBClient, bucket: str):
        self.client = influx_client
        self.bucket = bucket
        self.alert_state: Dict[str, datetime] = {}
        self.alert_history: List[dict] = []
    
    async def check_temperature_critical(self, sensor_type: str) -> Optional[dict]:
        threshold = float(os.getenv("TEMP_CRITICAL_THRESHOLD", 50))
        query = f'''\
        from(bucket: "{self.bucket}")
          |> range(start: -1m)
          |> filter(fn: (r) => r["_measurement"] == "sensor_reading")
          |> filter(fn: (r) => r["sensor_type"] == "{sensor_type}")
          |> filter(fn: (r) => r["_field"] == "temperature_c")
          |> last()
        '''
        try:
            result = self.client.query_api().query(query)
            for table in result:
                for record in table.records:
                    temp = record.get_value()
                    timestamp = record.get_time()
                    if temp > threshold:
                        alert_key = f"temp_critical_{sensor_type}"
                        if self._can_send_alert(alert_key, cooldown_minutes=10):
                            sensor_name = "BMP180" if sensor_type == "pressure" else sensor_type
                            alert = {
                                "id": f"{alert_key}_{int(timestamp.timestamp())}",
                                "timestamp": timestamp.isoformat(),
                                "level": "CRITICAL",
                                "sensor_id": sensor_type,
                                "sensor_type": sensor_type,
                                "metric": "temperature",
                                "value": round(temp, 2),
                                "threshold": threshold,
                                "message": f"🚨 {sensor_name} 센서 온도 임계값 초과! {temp:.1f}°C (기준: {threshold}°C)"
                            }
                            self._save_alert_history(alert)
                            logger.warning(f"ALERT: {alert['message']}")
                            return alert
        except Exception as e:
            logger.error(f"Temperature check failed for {sensor_type}: {e}")
        return None
