import rpyc
from rpyc.utils.server import ThreadedServer
from raft_server import Raft

class RaftService(rpyc.Service):
    """
    RPyC Service exposing RAFT node methods via RPC
    Handles both:
    - Internal RAFT communication (leader election, log replication)
    - Client operations (read/write)
    """
    
    def __init__(self):
        super().__init__()
        # Will be set from run_server()
        self._raft = None
    
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


def run_server(host="127.0.0.1", port=5001, node_id=0, peers_config=None):
    """
    Start the RPyC server for a RAFT node
    
    Args:
        host: Hostname to listen on (default: localhost)
        port: Port to listen on (default: 5001)
        node_id: Unique ID for this node (default: 0)
        peers_config: Dict mapping peer_id to {host, port}
                     Example: {1: {"host": "127.0.0.1", "port": 5002}, ...}
    
    Example:
        peers = {
            1: {"host": "127.0.0.1", "port": 5001},
            2: {"host": "127.0.0.1", "port": 5002},
            3: {"host": "127.0.0.1", "port": 5003},
        }
        run_server(host="127.0.0.1", port=5001, node_id=0, peers_config=peers)
    """
    
    # Create RAFT node
    raft_node = Raft(
        node_id=node_id,
        peers_config=peers_config if peers_config else {},
        logs_file_path=f"raft_node_{node_id}.log"
    )
    
    # Create RPC service
    service = RaftService()
    service._raft = raft_node
    
    # Start election timer thread
    raft_node.start_raft_node()
    
    # Start heartbeat timer thread (for leaders)
    raft_node.heartbeat_thread.start()
    
    # Start RPC server
    server = ThreadedServer(
        service,
        hostname=host,
        port=port,
        nbThreads=100  # Support up to 100 concurrent RPC calls
    )
    
    print(f"[Node {node_id}] RPyC Server listening on {host}:{port}")
    print(f"[Node {node_id}] Peers: {peers_config if peers_config else 'None'}")
    
    try:
        server.start()
    except KeyboardInterrupt:
        print(f"\n[Node {node_id}] Shutting down...")
        raft_node.kill()
        server.close()


if __name__ == "__main__":
    # Single node startup for testing
    try:
        run_server(host="127.0.0.1", port=5001, node_id=0)
    except KeyboardInterrupt:
        print("Server shutting down")