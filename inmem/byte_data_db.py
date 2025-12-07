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
        print(f'record here: {record}')
        
        if not record:
            return None
        
        # ✅ DEBUG: Print all fields in the record
        print(f'[DEBUG] Record fields dict: {record.fields}')
        print(f'[DEBUG] All field names in record: {list(record.fields.keys())}')
        print(f'[DEBUG] Looking for field: "{field}"')
        print(f'[DEBUG] Field exists? {field in record.fields}')
        
        # ✅ DEBUG: Print details of each field
        for field_name, field_obj in record.fields.items():
            print(f'[DEBUG] Field "{field_name}":')
            print(f'  - Type: {type(field_obj)}')
            print(f'  - Value: {field_obj.value}')
            print(f'  - Created at: {field_obj.created_at}')
            print(f'  - TTL: {field_obj.ttl}')
            print(f'  - Is alive at {timestamp}? {field_obj.is_alive(timestamp)}')
        
        result = record.get_field(field, timestamp)
        print(f'[DEBUG] get_field("{field}", {timestamp}) returned: {result}')
        
        return result

    def delete_at(self, key: str, field: str, timestamp: int) -> bool:
        record = self._store.get(key)
        if not record:
            return False
        deleted = record.delete_field(field, timestamp)
        # if record empty, cleanup key
        if deleted and not record.fields:
            del self._store[key]
        return deleted
