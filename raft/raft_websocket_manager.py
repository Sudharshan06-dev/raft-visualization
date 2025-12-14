# raft/raft_websocket_manager.py - FIXED VERSION

import json
import threading
import asyncio
from datetime import datetime
from typing import Dict, List
from fastapi import WebSocket

class WebSocketManager:
    _instance = None

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.lock = threading.Lock()
        self.event_loop: asyncio.AbstractEventLoop | None = None  # ← FIX: Store the running loop
        print("WebSocketManager initialized")

    @classmethod
    def get_ws_manager(cls) -> "WebSocketManager":
        if cls._instance is None:
            cls._instance = WebSocketManager()
        return cls._instance

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """CRITICAL: Call this from the running FastAPI thread to register the loop"""
        self.event_loop = loop
        print(f"WebSocketManager event loop set: {id(loop)}")

    def _make_serializable(self, obj):
        if obj is None:
            return None
        if isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, dict):
            try:
                return {str(k): self._make_serializable(v) for k, v in obj.items()}
            except Exception:
                return str(obj)
        if isinstance(obj, (list, tuple)):
            try:
                return [self._make_serializable(v) for v in obj]
            except Exception:
                return str(obj)
        try:
            return str(obj)
        except Exception:
            return "unknown"

    async def add_client(self, websocket: WebSocket):
        with self.lock:
            self.clients.add(websocket)
            print(f"Client connected. Total clients: {len(self.clients)}")

    async def remove_client(self, websocket: WebSocket):
        with self.lock:
            self.clients.discard(websocket)
            print(f"Client disconnected. Total clients: {len(self.clients)}")

    async def broadcast_heartbeat(
        self,
        leader_id: str,
        current_term: int,
        last_log_index: int,
        last_log_term: int,
        followers: List[str],
        peer_responses: Dict | None = None,
    ):
        
        print("broadcast_heartbeat EXECUTING")  # Debug: Confirm execution
        if peer_responses is None:
            peer_responses = {}

        message = {
            "type": "heartbeat",
            "leader_id": str(leader_id),
            "current_term": int(current_term),
            "last_log_index": int(last_log_index),
            "last_log_term": int(last_log_term),
            "followers": [str(f) for f in followers],
            "timestamp": datetime.utcnow().isoformat(),
            "responses": self._make_serializable(peer_responses),
        }
        await self._broadcast_now(message)

    async def broadcast_peer_response(self, leader_id: str, peer_id: str,
                                      success: bool, result):
        if result is None:
            result = {}
            
        result = self._make_serializable(result)

        message = {
            "type": "peer_response",
            "leader_id": str(leader_id),
            "peer_id": str(peer_id),
            "success": bool(success),
            "timestamp": datetime.utcnow().isoformat(),
            "result": result,
        }
        await self._broadcast_now(message)

    async def broadcast_node_state_change(self, node_id: str, new_state: str, current_term: int):
        message = {
            "type": "node_state_change",
            "node_id": str(node_id),
            "new_state": str(new_state),
            "current_term": int(current_term),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._broadcast_now(message)

    async def broadcast_log_entry(self, node_id: str, log_entry: Dict, log_index: int, committed: bool = False):
        message = {
            "type": "log_entry",
            "node_id": str(node_id),
            "log_entry": self._make_serializable(log_entry),
            "log_index": int(log_index),
            "committed": bool(committed),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._broadcast_now(message)

    async def _broadcast_now(self, message: Dict):
        if not self.clients:
            return

        try:
            message_json = json.dumps(message)
        except Exception as e:
            print(f"[WebSocketManager] JSON serialization failed: {e}")
            return

        disconnected: list[WebSocket] = []

        with self.lock:
            clients_snapshot = list(self.clients)

        for client in clients_snapshot:
            try:
                await client.send_text(message_json)
            except Exception as e:
                print(f"[WebSocketManager] Error sending to client: {e}")
                disconnected.append(client)

        for client in disconnected:
            await self.remove_client(client)

    def get_client_count(self) -> int:
        with self.lock:
            return len(self.clients)