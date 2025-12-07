from typing import Dict, Any
from inmem.kv_command import deserialize_command, CommandType
from inmem.byte_data_db import ByteDataDB


class StateMachineApplier:
    """Applies RAFT log commands to the ByteDataDB state machine."""
    
    def __init__(self, db: ByteDataDB):
        self.db = db
    
    def apply(self, command_str: str) -> Dict[str, Any]:
        """Apply a serialized command to the state machine."""
        try:
            command = deserialize_command(command_str)
            cmd_type = command.get("type")
            
            if cmd_type == CommandType.SET.value:
                return self._apply_set(command)
            elif cmd_type == CommandType.DELETE.value:
                return self._apply_delete(command)
            else:
                return {
                    "success": False,
                    "error": f"Unknown command type: {cmd_type}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to apply command: {e}"
            }
    
    def _apply_set(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Apply SET command."""
        self.db.set_at(
            command["key"],
            command["field"],
            command["value"],
            command["timestamp"],
            command.get("ttl")
        )
        return {
            "success": True,
            "operation": "SET",
            "key": command["key"],
            "field": command["field"]
        }
    
    def _apply_delete(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Apply DELETE command."""
        deleted = self.db.delete_at(
            command["key"],
            command["field"],
            command["timestamp"]
        )
        return {
            "success": True,
            "operation": "DELETE",
            "key": command["key"],
            "deleted": deleted
        }