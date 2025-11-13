import asyncio, random, math, datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MOBY Mock Sensor + Alerts")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message):
        for ws in list(self.active_connections):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)

sensor_manager = ConnectionManager()
alert_manager = ConnectionManager()

@app.websocket("/ws/sensor")
async def ws_sensor(websocket: WebSocket):
    await sensor_manager.connect(websocket)
    print("Sensor client connected")
    try:
        while True:
            now = datetime.datetime.utcnow().isoformat()
            vx = round(math.sin(datetime.datetime.utcnow().timestamp()) + random.uniform(-0.1, 0.1), 3)
            vy = round(math.cos(datetime.datetime.utcnow().timestamp()) + random.uniform(-0.1, 0.1), 3)
            vz = round(random.uniform(-1.0, 1.0), 3)
            mag = round(math.sqrt(vx**2 + vy**2 + vz**2), 3)

            data = {
                "device_id": "Motor_A_01",
                "sensor_type": "multi_vib_temp_rpm",
                "timestamp": now,
                "temperature": round(25 + random.uniform(-2, 2), 2),
                "rpm": int(1000 + random.uniform(-50, 50)),
                "vibration": {"x": vx, "y": vy, "z": vz, "magnitude": mag}
            }
            await websocket.send_json(data)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        sensor_manager.disconnect(websocket)

@app.websocket("/ws")
async def ws_alerts(websocket: WebSocket):
    await alert_manager.connect(websocket)
    print("Alerts client connected")
    try:
        while True:
            await asyncio.sleep(random.randint(8, 15))
            if random.random() < 0.7:
                msg = {
                    "type": "alert",
                    "payload": {
                        "id": f"alert_{int(datetime.datetime.utcnow().timestamp())}",
                        "level": random.choice(["info", "warning", "critical"]),
                        "message": random.choice([
                            "Temperature exceeds threshold",
                            "Vibration anomaly detected",
                            "Motor RPM fluctuation observed",
                            "All systems normal"
                        ]),
                        "ts": datetime.datetime.utcnow().isoformat(),
                        "source": "edge",
                        "llm_summary": random.choice([
                            "AI: Immediate attention required",
                            "AI: Monitor situation closely",
                            "AI: No action needed"
                        ])
                    }
                }
                await alert_manager.broadcast(msg)
                print(f"[ALERT] {msg['payload']['message']}")
            if random.random() < 0.3:
                report = {
                    "type": "report",
                    "payload": {
                        "id": f"R{int(datetime.datetime.utcnow().timestamp())}",
                        "title": "System Health Report",
                        "llm_summary": random.choice([
                            "Anomaly report generated",
                            "System health summary",
                            "AI analysis complete"
                        ]),
                        "ts": datetime.datetime.utcnow().isoformat()
                    }
                }
                await alert_manager.broadcast(report)
    except WebSocketDisconnect:
        alert_manager.disconnect(websocket)

@app.get("/api/alerts/history")
async def get_alert_history(limit: int = 10):
    now = datetime.datetime.utcnow()
    return [
        {
            "id": f"alert_{i}",
            "level": random.choice(["info", "warning", "critical"]),
            "message": random.choice(["Mock alert", "High vibration", "Temperature deviation"]),
            "llm_summary": random.choice(["AI: Requires monitoring", "AI: Normal", "AI: Check status"]),
            "ts": (now - datetime.timedelta(seconds=i * 60)).isoformat(),
            "source": "edge"
        }
        for i in range(limit)
    ]
