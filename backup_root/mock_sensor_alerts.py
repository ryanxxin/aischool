'''
Backup of root-level mock_sensor_alerts.py
'''
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
