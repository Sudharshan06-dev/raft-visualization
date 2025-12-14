"""
websocket_server.py - FIXED VERSION
FastAPI WebSocket server for RAFT visualization with proper event loop handling
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import uvicorn
import asyncio
from raft.raft_websocket_manager import WebSocketManager

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get singleton WebSocket manager
ws_manager = WebSocketManager.get_ws_manager()


@app.on_event("startup")
async def startup_event():
    """
    CRITICAL: Register the running event loop with WebSocketManager
    This is called when uvicorn starts the app
    """
    loop = asyncio.get_event_loop()
    ws_manager.set_event_loop(loop)
    print(f"FastAPI startup: WebSocketManager loop registered (id={id(loop)})")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await ws_manager.add_client(websocket)
    print(f"Client connected. Total clients: {ws_manager.get_client_count()}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                print(f"📨 Received from client: {message}")
            except Exception:
                pass
    except WebSocketDisconnect:
        await ws_manager.remove_client(websocket)
        print(f"Client disconnected. Total clients: {ws_manager.get_client_count()}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await ws_manager.remove_client(websocket)
        except Exception:
            pass


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "connected_clients": ws_manager.get_client_count(),
        "event_loop_registered": ws_manager.event_loop is not None
    }


def get_ws_manager():
    """Get the WebSocket manager instance"""
    return ws_manager


if __name__ == "__main__":
    print("WebSocket server starting on ws://0.0.0.0:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765)