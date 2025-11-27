from __future__ import annotations
from typing import Dict, Optional
from .byte_data_record import ByteDataRecord

class ByteDataDB:
    """Main in-memory DB supporting CRUD, TTL, scan and backup/restore."""
    _instance = None

    def __init__(self):
        self._store: Dict[str, ByteDataRecord] = {}

    @classmethod
    def get_instance(cls) -> "ByteDataDB":
        if cls._instance is None:
            cls._instance = ByteDataDB()
        return cls._instance

    # ------------------------------------------------------------------
    # Core timestamped CRUD operations
    # ------------------------------------------------------------------
    def set_at(self, key: str, field: str, value: str, timestamp: int, ttl: Optional[int] = None) -> None:
        if key not in self._store:
            self._store[key] = ByteDataRecord()
        self._store[key].set_field(field, value, timestamp, ttl)
    
    def get_entire_data(self):
        return self._store
    
    def clear_entire_data(self):
        return self._store.clear()
    
    def get_record(self, key: str) -> Optional[ByteDataRecord]:
        return self._store.get(key)

    def get_at(self, key: str, field: str, timestamp: int) -> Optional[str]:
        record = self._store.get(key)
        if not record:
            return None
        return record.get_field(field, timestamp)

    def delete_at(self, key: str, field: str, timestamp: int) -> bool:
        record = self._store.get(key)
        if not record:
            return False
        deleted = record.delete_field(field, timestamp)
        # if record empty, cleanup key
        if deleted and not record.fields:
            del self._store[key]
        return deleted
