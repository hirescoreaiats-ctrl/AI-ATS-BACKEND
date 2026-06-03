from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/realtime", tags=["realtime"])


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, workspace_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(workspace_id, []).append(websocket)

    def disconnect(self, workspace_id: str, websocket: WebSocket):
        sockets = self.active.get(workspace_id, [])
        if websocket in sockets:
            sockets.remove(websocket)

    async def broadcast(self, workspace_id: str, message: dict):
        for socket in list(self.active.get(workspace_id, [])):
            await socket.send_json(message)


manager = ConnectionManager()


@router.websocket("/workspace/{workspace_id}")
async def workspace_socket(websocket: WebSocket, workspace_id: str):
    await manager.connect(workspace_id, websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            await manager.broadcast(workspace_id, payload)
    except WebSocketDisconnect:
        manager.disconnect(workspace_id, websocket)
