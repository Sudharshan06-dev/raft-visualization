from typing import List, Optional
from .byte_data_db import ByteDataDB


class InMemorySearch:
    """Search/scan helper that operates against a `ByteDataDB` instance.

    By default it uses the singleton `ByteDataDB.get_instance()` so scans
    will see data written through the same DB.
    """

    def __init__(self, db: Optional[ByteDataDB] = None):
        self._db = db or ByteDataDB.get_instance()

    def scan_at(self, key: str, timestamp: int) -> List[str]:
        record = self._db.get_record(key=key)
        if not record:
            return []
        return [f"{f}({v})" for f, v in record.scan_fields(timestamp)]

    def scan_by_prefix_at(self, key: str, prefix: str, timestamp: int) -> List[str]:
        record = self._db.get_record(key=key)
        if not record:
            return []
        return [f"{f}({v})" for f, v in record.scan_fields_by_prefix(prefix, timestamp)]
