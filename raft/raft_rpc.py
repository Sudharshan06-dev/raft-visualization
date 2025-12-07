import rpyc
from rpyc.utils.server import ThreadedServer
from raft.raft_server import Raft
from inmem.byte_data_db import ByteDataDB
from inmem.state_machine_applier import StateMachineApplier

class RaftService(rpyc.Service):
    """
    RPyC Service exposing RAFT node methods via RPC
    Handles both:
    - Internal RAFT communication (leader election, log replication)
    - Client operations (read/write)
    """
    
    def __init__(self, raft: Raft, db: ByteDataDB):
        super().__init__()
        # Will be set from run_server()
        self._raft = raft
        self._db = db
    
    # ==================== PHASE 1: LEADER ELECTION ====================
    
    def exposed_send_vote_request(self, vote_arguments):
        """
        RPC ENDPOINT: RequestVote RPC receiver (§5.1, §5.4)
        Called by: Remote candidate nodes
        
        Args:
            vote_arguments: VoteArguments object
                - current_term: Candidate's term
                - candidate_id: Who's running for leader
                - last_log_index: Candidate's last log index
                - last_log_term: Candidate's last log term
        
        Returns:
            bool: True if vote granted, False if rejected
        """
        return self._raft.handle_request_vote(vote_arguments)
    
    # ==================== PHASE 2: LOG REPLICATION ====================
    
    def exposed_send_health_check_request(self, health_check_arguments):
        """
        RPC ENDPOINT: AppendEntries RPC receiver (§5.3)
        Called by: Leader (or candidate) with log entries or heartbeat
        
        Args:
            health_check_arguments: HealthCheckArguments object
                - current_term: Leader's term
                - leader_id: Who's the leader
                - prev_log_index: Index of log entry before new ones
                - prev_log_term: Term of prevLogIndex entry
                - entries: Log entries to append (empty for heartbeat)
                - leader_commit: Leader's commitIndex
        
        Returns:
            dict: {"success": bool, "term": int}
                - success=True: Entries accepted/appended
                - success=False: Log mismatch (leader will retry)
        """
        return self._raft.handle_health_check_request(health_check_arguments)
    
    # ==================== CLIENT OPERATIONS ====================
    
    def exposed_append_log_entries(self, command):
        """
        RPC ENDPOINT: Client write request
        Called by: Client application to write data
        
        Args:
            command: String command to replicate (e.g., "SET x=100", "DELETE key")
        
        Returns:
            dict: {
                "success": bool,
                "index": int (log index if leader),
                "term": int (current term if leader),
                "error": str (if not leader),
                "message": str
            }
        """
        return self._raft.append_log_entries(command)
    
    def exposed_read_log(self, index):
        """
        RPC ENDPOINT: Client read request
        Called by: Client application to read data
        
        Args:
            index: Log index to read
        
        Returns:
            dict: {
                "success": bool,
                "entry": dict (log entry if found),
                "committed": bool (if entry is committed),
                "error": str (if index not found)
            }
        """
        return self._raft.read_log(index)

    # ==================== LEADER DISCOVERY ====================
    
    def exposed_get_leader(self):
        """Get current leader info for client routing."""
        return self._raft.get_leader_info()
    
    # ==================== KV STORE READS (DIRECT FROM STATE MACHINE) ====================
    
    def exposed_read_kv(self, key: str, field: str, timestamp: int):
        """Read from committed state machine."""
        value = self._db.get_at(key, field, timestamp)
        if value is not None:
            return {"success": True, "value": value}
        return {"success": False, "value": "NOT_FOUND"}
    
    def exposed_scan_kv(self, key: str, timestamp: int):
        """Scan all fields for a key."""
        record = self._db.get_record(key)
        if not record:
            return {"success": True, "fields": []}
        return {"success": True, "fields": record.scan_fields(timestamp)}
    
    def exposed_scan_kv_by_prefix(self, key: str, prefix: str, timestamp: int):
        """Scan fields by prefix."""
        record = self._db.get_record(key)
        if not record:
            return {"success": True, "fields": []}
        return {"success": True, "fields": record.scan_fields_by_prefix(prefix, timestamp)}


def run_server(host="127.0.0.1", port=5001, node_id=0, peers_config=None):
    
    # Create shared ByteDataDB instance for this node
    db = ByteDataDB.get_instance()
    
    # Create state machine applier
    applier = StateMachineApplier(db)
    
    # Create RAFT node with the applier
    raft_node = Raft(
        node_id=node_id,
        peers_config=peers_config if peers_config else {},
        logs_file_path=f"raft_node_{node_id}.log",
        state_machine_applier=applier  # <-- Pass applier to RAFT
    )
    
    # Create RPC service with both RAFT and DB
    service = RaftService(raft_node, db)
    
    # Start RAFT threads
    raft_node.start_raft_node()
    raft_node.heartbeat_thread.start()
    
    # Start RPC server
    server = ThreadedServer(
        service,
        hostname=host,
        port=port,
        protocol_config={"allow_public_attrs": True}
    )
    
    print(f"[Node {node_id}] Server on {host}:{port}")
    
    try:
        server.start()
    except KeyboardInterrupt:
        print(f"\n[Node {node_id}] Shutting down...")
        raft_node.kill()
        server.close()


if __name__ == "__main__":
    run_server(host="127.0.0.1", port=5001, node_id=0)