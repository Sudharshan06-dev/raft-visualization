from typing import List, Tuple, Optional, Dict
import copy
from .byte_data_db import ByteDataDB


class ByteDataBackupEngine:
    """
    Manages in-memory backups (snapshots) of the active DB state.
    """

    def __init__(self) -> None:
        self._target = ByteDataDB.get_instance()
        self._backups: List[Tuple[int, Dict[str, Dict[str, Tuple[str, Optional[int]]]]]] = []

    # Level 4: backup
    def backup(self, timestamp: int) -> int:
        count = 0
        snapshot: Dict[str, Dict[str, Tuple[str, Optional[int]]]] = {}

        for key, record in self._target.get_entire_data().items():
            active_fields: Dict[str, Tuple[str, Optional[int]]] = {}
            for fname, f in record.fields.items():
                if f.is_alive(timestamp):
                    remaining_ttl = None if f.ttl is None else (f.created_at + f.ttl) - timestamp
                    active_fields[fname] = (f.value, remaining_ttl)
            if active_fields:
                snapshot[key] = active_fields
                count += 1

        # store a deep copy so later mutations don't change previous backups
        self._backups.append((timestamp, copy.deepcopy(snapshot)))
        return count

    def restore(self, timestamp: int, timestamp_to_restore: int) -> None:
        candidate = None
        for b_time, snap in self._backups:
            if b_time <= timestamp_to_restore:
                candidate = (b_time, snap)
            else:
                break

        if candidate is None:
            return

        _, snapshot = candidate
        self._target.clear_entire_data()

        for key, fields in snapshot.items():
            for field_name, (value, remaining_ttl) in fields.items():
                # Use the restore-time as the created_at for restored fields and
                # reapply remaining TTL (which may be None)
                self._target.set_at(key, field_name, value, timestamp, remaining_ttl)
