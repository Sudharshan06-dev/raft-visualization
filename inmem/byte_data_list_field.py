from typing import Optional, List
from .IByteDataField import IByteDataField

class ByteDataListField(IByteDataField):

    def __init__(self, value: Optional[List] = None, created_at: int = 0, ttl: Optional[int] = None):
        # Initialize with a copy to avoid external mutation and support empty lists
        self.value = list(value) if value else []
        self.created_at = created_at
        self.ttl = ttl

    def append(self, item) -> None:
        self.value.append(item)

    def is_alive(self, timestamp: int) -> bool:
        if self.ttl is None:
            return True
        return timestamp <= self.created_at + self.ttl
