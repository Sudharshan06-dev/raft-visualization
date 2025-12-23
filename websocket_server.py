"""
websocket_server.py - RAFT Consensus with KV Store Integration
FastAPI WebSocket server with KV client endpoint for log replication
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import json
import uvicorn
from inmem.kv_client import KVClient
import asyncio
from raft.raft_websocket_manager import WebSocketManager
import time

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

CLUSTER_CONFIG = {
    "A": {"host": "127.0.0.1", "port": 5001},
    "B": {"host": "127.0.0.1", "port": 5002},
    "C": {"host": "127.0.0.1", "port": 5003},
}


class KvItem(BaseModel):
    type: str
    command: str
    key: str
    field: str
    value: str


@app.on_event("startup")
async def startup_event():
    """
    Register the running event loop with WebSocketManager
    Called when uvicorn starts the app
    """
    loop = asyncio.get_event_loop()
    ws_manager.set_event_loop(loop)
    print(f"FastAPI startup: WebSocketManager loop registered (id={id(loop)})")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await ws_manager.add_client(websocket)
    print(f"WebSocket client connected. Total clients: {ws_manager.get_client_count()}")
    
    #Sync state immediately when client connects
    await ws_manager.on_client_connect()

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                print(f"📨 Received from client: {message}")
            except Exception as e:
                print(f"Failed to parse message: {e}")
    except WebSocketDisconnect:
        await ws_manager.remove_client(websocket)
        print(f"WebSocket client disconnected. Total clients: {ws_manager.get_client_count()}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await ws_manager.remove_client(websocket)
        except Exception:
            pass


@app.post("/kv-store")
async def write_kv_store(kv_item: KvItem):
    try:
        print(f"\n{'='*60}")
        print(f"KV Store Write Request")

        # Get current timestamp (microseconds)
        timestamp = int(time.time() * 1_000_000)
        print(f"Timestamp: {timestamp}")

        # Create KV client - connects to cluster
        # Client will automatically find the leader
        client = KVClient(CLUSTER_CONFIG)
        
        # Call set on the cluster (will be routed to leader)
        # This initiates log replication across the cluster
        result = client.set(
            key=str(kv_item.key),
            field=str(kv_item.field),
            value=str(kv_item.value),
            timestamp=timestamp,
            ttl=None  # No TTL for now
        )

        print(f"KVClient.set() returned: {result}")
        
        return {
            "success": True,
            "message": "KV store entry submitted for replication",
            "key": kv_item.key,
            "field": kv_item.field,
            "value": kv_item.value,
            "timestamp": timestamp,
            "result": result if result else "Entry appended to leader's log"
        }

    except ConnectionError as e:
        print(f"Connection Error: {e}")
        return {
            "success": False,
            "error": "CONNECTION_ERROR",
            "message": f"Failed to connect to cluster: {str(e)}",
            "details": "Make sure start_cluster.py has started the RAFT nodes"
        }, 503

    except TimeoutError as e:
        print(f"Timeout Error: {e}")
        return {
            "success": False,
            "error": "TIMEOUT_ERROR",
            "message": f"Cluster operation timed out: {str(e)}",
            "details": "Leader may be unavailable or nodes are slow to respond"
        }, 504

    except Exception as e:
        print(f"Unexpected Error: {type(e).__name__}: {e}")
        return {
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": f"Error writing to KV store: {str(e)}",
            "exception_type": type(e).__name__
        }, 500

@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Try to connect to cluster to verify it's alive
        client = KVClient(CLUSTER_CONFIG)
        cluster_healthy = True
    except Exception as e:
        print(f"Cluster health check failed: {e}")
        cluster_healthy = False

    return {
        "status": "ok",
        "websocket": {
            "connected_clients": ws_manager.get_client_count(),
            "event_loop_registered": ws_manager.event_loop is not None
        },
        "cluster": {
            "healthy": cluster_healthy,
            "config": CLUSTER_CONFIG
        }
    }

@app.get("/cluster/status")
async def cluster_status():
    """Get cluster status"""
    return {
        "nodes": CLUSTER_CONFIG,
        "node_count": len(CLUSTER_CONFIG),
        "description": "RAFT cluster with 3 nodes (A, B, C)"
    }


def get_ws_manager():
    """Get the WebSocket manager instance"""
    return ws_manager


if __name__ == "__main__":
    print("\n" + "="*60)
    print(f"Cluster Config: {CLUSTER_CONFIG}")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8765)