from dataclasses import dataclass, field
from typing import List

@dataclass
class HealthCheckArguments:
    """AppendEntries RPC Arguments (Raft Paper §5.3)"""
    current_term: int              # Leader's term
    leader_id: int                 # For followers to redirect clients
    prev_log_index: int            # Index of log entry immediately preceding new ones
    prev_log_term: int             # Term of prevLogIndex entry
    entries: List[dict] = field(default_factory=list)  # Log entries to replicate (empty for heartbeat)
    leader_commit: int = 0         # Leader's commitIndex