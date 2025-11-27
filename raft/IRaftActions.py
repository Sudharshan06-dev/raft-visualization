from abc import ABC, abstractmethod

class IRaftActions(ABC):
    """
    Abstract base class defining all RAFT node operations
    Implements Phase 1 (Leader Election) and Phase 2 (Log Replication)
    Raft Paper: http://nil.csail.mit.edu/6.824/2020/papers/raft-extended.pdf
    """
    
    # ==================== INITIALIZATION ====================
    
    @abstractmethod
    def add_peer_connections(self, peers_config):
        """
        Set up peer connections after node initialization
        Called once during startup before any elections
        
        Args:
            peers_config: Dict mapping peer_id to {host, port}
        """
        pass
    
    # ==================== PHASE 1: LEADER ELECTION ====================
    
    @abstractmethod
    def reset_election_timer(self):
        """
        Reset the election timeout counter
        Called when:
        - Heartbeat received from leader (follower)
        - Vote granted request received (follower)
        Raft Paper §5.2
        """
        pass
    
    @abstractmethod
    def request_vote(self):
        """
        SENDER: Initiate leader election (§5.2)
        Called when election timeout fires
        
        Sends RequestVote RPC to all peers
        Increments currentTerm
        Votes for self
        Waits for majority votes
        Becomes leader if majority reached
        """
        pass
    
    @abstractmethod
    def handle_request_vote(self, vote_args):
        """
        RECEIVER: Process incoming RequestVote RPC (§5.1, §5.4)
        Called by remote candidate nodes
        
        Args:
            vote_args: VoteArguments with term, candidate_id, last_log_index, last_log_term
        
        Returns:
            bool: True if vote granted, False if rejected
        """
        pass
    
    # ==================== PHASE 2: LOG REPLICATION ====================
    
    @abstractmethod
    def send_health_checks(self):
        """
        LEADER ONLY: Send periodic heartbeats to followers (§5.3)
        Called every 100ms if node is leader
        
        Sends AppendEntries RPC with:
        - Log entries (or empty for heartbeat)
        - Previous log index/term for log matching
        - Leader's commitIndex
        
        Serves 3 purposes:
        1. Replicate log entries to followers
        2. Detect down followers (timeout)
        3. Prevent election timeouts (heartbeat resets timer)
        """
        pass
    
    @abstractmethod
    def handle_health_check_request(self, health_check_args):
        """
        RECEIVER: Process incoming AppendEntries RPC (§5.3)
        Called by leader with log entries or heartbeat
        
        Args:
            health_check_args: HealthCheckArguments with term, entries, prevLogIndex, etc.
        
        Returns:
            dict: {"success": bool, "term": int}
                - success=True: Entries appended/accepted
                - success=False: Log mismatch (leader will retry with earlier logs)
        """
        pass
    
    # ==================== CLIENT OPERATIONS ====================
    
    @abstractmethod
    def append_log_entries(self, command):
        """
        CLIENT WRITE: Append command to replicated log
        Can be called on leader (accepted) or follower (rejected)
        
        Args:
            command: String command to replicate (e.g., "SET x=100")
        
        Returns:
            dict: {
                "success": bool,
                "index": int (if leader),
                "error": str (if not leader)
            }
        """
        pass
    
    @abstractmethod
    def read_log(self, index):
        """
        CLIENT READ: Fetch log entry or state
        Leader: Can serve both committed and uncommitted entries
        Follower: Only serves committed entries
        
        Args:
            index: Log index to read
        
        Returns:
            dict: {
                "success": bool,
                "entry": dict (if found),
                "committed": bool,
                "error": str (if not found)
            }
        """
        pass
    
    @abstractmethod
    def apply_to_state_machine(self):
        """
        Apply all newly-committed entries to state machine
        Called when commitIndex advances
        
        Executes commands from lastApplied+1 to commitIndex
        Transitions: log entry → applied state
        """
        pass