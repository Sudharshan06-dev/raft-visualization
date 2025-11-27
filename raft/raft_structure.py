from dataclasses import dataclass, field
from typing import Dict, List
from raft_state import RaftState

@dataclass
class RaftStructure:
    
    '''
    All the terms here are persistent variables -> stored to the disk 
    When the server restarts or when it crashes it should know these variables to comeback to the network
    '''
    id: int # To indicate which server / node id
    current_term: int # To indicate the current term of the node -> specific to the this node
    voted_for: int # To indicate which server among its peer it voted for (-1 means no vote cast yet)
    logs_file_path: str # To hold the path to the AOF file on disk
    peers: Dict[int, Dict[str, str]] # Dict mapping peer_id to {host, port}
    
    '''
    All the terms here are volatile variables -> not stored to the disk 
    '''
    state: RaftState
    last_log_index: int # Index of last log entry (0 if no log entries)
    last_log_term: int # Term of last log entry (0 if no log entries)
    logs: List[Dict] = field(default_factory=list) # List of log entries, each entry is {term: int, command: any}
    commit_index: int = 0 #Index of highest log entry known to be committed (initialized to 0)
    election_timer: float = 0.5 #Election timeout value in seconds (randomized between 300-500ms)