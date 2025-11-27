from typing import Dict, Optional, List, Tuple
from .byte_data_field import ByteDataField


class ByteDataRecord:
    
    def __init__(self):
        self.fields: Dict[str, ByteDataField] = {}
    
    def set_field(self, field: str, value: str, timestamp: int, ttl: Optional[int] = None) -> None:
        self.fields[field] = ByteDataField(value, timestamp, ttl)
    
    def get_field(self, field: str, timestamp: int) -> Optional[str]:
        f = self.fields.get(field)
        if f and f.is_alive(timestamp):
            return f.value
        return None
    
    def delete_field(self, field: str, timestamp: int) -> bool:
        f = self.fields.get(field)
        if f and f.is_alive(timestamp):
            del self.fields[field]
            return True
        return False
    
    def scan_fields(self, timestamp: int) -> List[Tuple[str, str]]:
        result = [(k, f.value) for k, f in self.fields.items() if f.is_alive(timestamp=timestamp)]
        result.sort(key=lambda x: x[0])
        return result
    
    def scan_fields_by_prefix(self, prefix: str, timestamp: int) -> List[Tuple[str, str]]:
        # Filter by field name prefix (not value) — clearer intent for "by_prefix"
        result = [(k, f.value) for k, f in self.fields.items() if f.is_alive(timestamp=timestamp) and k.startswith(prefix)]
        result.sort(key=lambda x: x[0])
        return result
