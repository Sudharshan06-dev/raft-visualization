import json
from typing import List, Dict, Any, Optional
import enum

class CommandType(enum.Enum):
    SET = "SET"
    DELETE = "DELETE"

def create_set_command(key: str, field: str, value: str, timestamp: int, ttl: Optional[int] = None) -> Dict[str, Any]:
    """Create a SET command to be appended to RAFT log."""
    
    return {
        "type": CommandType.SET.value,
        "key": key,
        "field": field,
        "value": value,
        "timestamp": timestamp,
        "ttl": ttl
    }

def create_delete_command(key: str, field: str, timestamp: str):
    """Create a DELETE command to be appended to RAFT log."""
    return {
        "type": CommandType.DELETE.value,
        "key": key,
        "field": field,
        "timestamp": timestamp
    }

def serialize_command(command: Dict[str, Any]) -> str:
    """Serialize command to string for RAFT log storage."""
    return json.dumps(command)
    
def deserialize_command(command: str) -> Dict[str, Any]:
    """Deserialize command from RAFT log."""
    return json.loads(command)