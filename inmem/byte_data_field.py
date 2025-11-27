from typing import Optional
from .IByteDataField import IByteDataField

class ByteDataField(IByteDataField):

    def __init__(self, value: str, created_at: int, ttl: Optional[int]):
        self.value = value
        self.created_at = created_at
        self.ttl = ttl

    def is_alive(self, timestamp: int) -> bool:
        if self.ttl is None:
            return True
        return timestamp <= self.created_at + self.ttl
