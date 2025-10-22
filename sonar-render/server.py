# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
import asyncio
from typing import List

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

class ConnectionManager:
    def __init__(self):
        self.viewers: List[WebSocket] = []
        self.publishers: List[WebSocket] = []
        self.lock = asyncio.Lock()

    async def connect_viewer(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.viewers.append(ws)

    async def connect_publisher(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.publishers.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.viewers: self.viewers.remove(ws)
            if ws in self.publishers: self.publishers.remove(ws)

    async def broadcast_to_viewers(self, message: str):
        async with self.lock:
            for v in list(self.viewers):
                try:
                    await v.send_text(message)
                except Exception:
                    await self.disconnect(v)

manager = ConnectionManager()

@app.get("/")
async def index():
    return HTMLResponse(open("static/index.html","r",encoding="utf-8").read())

@app.websocket("/ws/publisher")
async def websocket_publisher(ws: WebSocket):
    await manager.connect_publisher(ws)
    try:
        while True:
            data = await ws.receive_text()
            await manager.broadcast_to_viewers(data)
    except WebSocketDisconnect:
        await manager.disconnect(ws)

@app.websocket("/ws/viewer")
async def websocket_viewer(ws: WebSocket):
    await manager.connect_viewer(ws)
    try:
        while True:
            # viewers may send keepalive pings; this keeps the connection open
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
