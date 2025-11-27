import rpyc
from rpyc.utils.server import ThreadedServer
from IRaftActions import IRaftActions
from raft_structure import RaftStructure
from raft_state import RaftState
import random
import concurrent.futures
import datetime
import json
import threading
from vote_arguments import VoteArguments
from health_check_arguments import HealthCheckArguments


class Raft(IRaftActions):
    """A Raft node that implements `IRaftActions` and holds a `RaftStructure`.

    For now methods are placeholders; the structure is stored on
    `self.raft_terms` and exposed to tests via RPC methods.
    """
    
    MIN_DELAY = 0.3 # 300ms is the minimum time to be added to the election timer
    MAX_DELAY = 0.5 # 500ms is the maximum time to be added to the election timer

    def __init__(self, node_id, peers_config=None, logs_file_path="raft_logs.txt"):
        # initialize raft structure with sensible defaults
        self._killed = False
        
        # ADDED: Thread safety lock for concurrent RPC access
        self.lock = threading.Lock()
        
        self.raft_terms: RaftStructure = RaftStructure(
            id=node_id,
            current_term=0,
            voted_for=-1,  # -1 means no vote cast in current term
            logs_file_path=logs_file_path,
            last_log_index=0,
            last_log_term=0,  # ADDED
            peers=peers_config if peers_config else {},
            state=RaftState.follower,
            logs=[]  # ADDED
        )
        
        # Load persistent state from disk if it exists - what if the server has crashed and it has restarted
        self._load_persistent_state()
        
        # ADDED: For leader log tracking
        self.next_index = {}        # Index of next log entry to send to each peer
        self.match_index = {}       # Index of highest replicated log entry on each peer
    
        # Initialize for all peers
        for peer_id in (peers_config if peers_config else {}).keys():
            self.next_index[peer_id] = len(self.raft_terms.logs)  # Start at my last log index
            self.match_index[peer_id] = 0
    
        # ADDED: Heartbeat timer thread
        self.heartbeat_timer_event = threading.Event()
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_ticker, daemon=True)
        
        self.election_timer_event = threading.Event()
        self.timer_thread = threading.Thread(target=self._ticker, args=(), daemon=True)
        
        # ADDED: For leader election tracking
        self.vote_count = 0 #To calculate the peer count for leader election -> check it against the majority
        self.received_votes = {} # To track the peer id response for leader election
    
    """Start the election timer thread"""
    def start_raft_node(self):
        self.timer_thread.start()
        self.heartbeat_thread.start()
    
    def add_peer_connections(self, peers_config):
        """Set up peer connections after node initialization"""
        self.raft_terms.peers = peers_config
    
    def reset_election_timer(self):
        """
        Signals the ticker to stop sleeping/waiting immediately
        and restart the countdown.
        """
        print(f"[Node {self.raft_terms.id}] Resetting timer NOW.")
        
        # Setting the event interrupts the 'wait' call in the ticker() loop
        
        if self.raft_terms.state != RaftState.leader:
            self.election_timer_event.set()
    
    #Main method -> a thread is invoked and it is run as a daemon to check for the timeout
    #If the event set function is called within the time, then election timer is reset again
    #If the election timer is fired, then it initiates for the leader election voting
    def _ticker(self):
        
        while not self.killed():
            
            # 1. Clear the event flag for the next cycle
            self.election_timer_event.clear()
            
            # 2. Randomize the timeout duration for the next cycle
            # We must do this before we start waiting
            new_timeout_ms = random.uniform(300, 500)
            self.raft_terms.election_timer = new_timeout_ms / 1000.0 # To yield the new timeout in ms and not in seconds
            
            print(f"[Node {self.raft_terms.id}] Ticker waiting for up to {self.raft_terms.election_timer:.3f}s...")
            
            # 3. Wait using event.wait(timeout)
            # it returns TRUE if set() was called -> if the health check function is reached before the timeout then the set is invoked
            # by another thread, or FALSE if the timeout was reached naturally.
            health_status_invoked = self.election_timer_event.wait(timeout=self.raft_terms.election_timer)
            
            #Before asking for the vote check if the node is active
            #Checking the worst scenarios first
            if self.killed():
                break
            
            #Check if the leader invokes the health check up
            #If the events occurs then we have to again reset the timer for the election timeout
            if health_status_invoked:
                print(f"[Node {self.raft_terms.id}] Health check received, resetting timer")
                continue
            
            # Election timeout fired -> start leader election
            print(f"[Node {self.raft_terms.id}] Election timeout! Starting election...")
            self.request_vote()
    
    # -----------------------------
    # Append log entries
    # -----------------------------
    
    def append_log_entries(self, command):
        
        """
        PHASE 2: LOG REPLICATION - Client write request
        Raft Paper §5.3
        
        1. Only leader accepts writes
        2. Append to leader's log
        3. Replicate to followers (via send_health_checks)
        4. When majority replicates, advance commitIndex
        5. When commitIndex > lastApplied, apply to state machine
        """
        
        try:
            
            with self.lock:
                
                # Rule 1: Only leader accepts writes
                if self.raft_terms.state != RaftState.leader:
                    
                    return {
                        "success": False,
                        "error": "not leader",
                        "leader_id": None  # Client should redirect
                    }
                
                # Rule 2: Append to own log immediately
                log_entry = {
                    "term": self.raft_terms.current_term,
                    "command": command,
                    "index": len(self.raft_terms.logs)
                }
                
                self.raft_terms.logs.append(log_entry)
                self.raft_terms.last_log_index = len(self.raft_terms.logs) - 1
                self.raft_terms.last_log_term = self.raft_terms.current_term
            
                # Rule 3: Persist to disk immediately (required by Raft)
                self._persist_log_entry(log_entry)
                
                print(f"[Node {self.raft_terms.id}] Appended log entry at index {log_entry['index']}")

                # Rule 4: Return to client
                # Client can:
                # - Poll to check if committed
                # - Or just wait (entries will be replicated in background)
                return {
                    "success": True,
                    "index": log_entry["index"],
                    "term": self.raft_terms.current_term,
                    "message": "Appended to leader log, waiting for replication"
                }
                
        except Exception as e:
            print(f"[Node {self.raft_terms.id}] Error persisting state: {e}")
            return -1
    
    def _persist_log_entry(self, log_entry):
        """Persist a single log entry to disk"""
        try:
            with open(self.raft_terms.logs_file_path, 'a') as f:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "node_id": self.raft_terms.id,
                    "index": log_entry["index"],
                    "term": log_entry["term"],
                    "command": log_entry["command"]
                }
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            print(f"[Node {self.raft_terms.id}] Error persisting log: {e}")
    
    def get_committed_log_entry(self, index):
        """
        Read from state machine
        Only return if entry is COMMITTED
        Can be called by followers or clients
        """
    
        with self.lock:
            # Only return if committed
            if index > self.raft_terms.commit_index:
                return {
                    "success": False,
                    "error": "not committed yet",
                    "committed_index": self.raft_terms.commit_index
                }
            
            # Return committed entry
            if index < len(self.raft_terms.logs):
                return {
                    "success": True,
                    "entry": self.raft_terms.logs[index]
                }
            
            return {
                "success": False,
                "error": "index out of range"
            }

    def read_log(self, index):
        """
        Read-only query
        Raft Paper §5.3

        Followers CAN serve reads if entry is committed
        Leader can serve both committed AND uncommitted
        """
    
        with self.lock:
            # Check if index exists
            if index >= len(self.raft_terms.logs):
                return {
                    "success": False,
                    "error": "index not found"
                }
            
            entry = self.raft_terms.logs[index]
            is_committed = index <= self.raft_terms.commit_index
            
            # FOLLOWERS: Can only serve committed reads
            if self.raft_terms.state == RaftState.follower:
                if not is_committed:
                    return {
                        "success": False,
                        "error": "not committed yet, ask leader"
                    }
            
            # LEADER: Can serve committed and uncommitted
            return {
                "success": True,
                "entry": entry,
                "committed": is_committed,
                "commit_index": self.raft_terms.commit_index
            }
            
    # -----------------------------
    # Leader election (sender/receiver)
    # -----------------------------
    
    def request_vote(self):
        """
        PHASE 1: LEADER ELECTION - Sender Implementation
        Raft Paper §5.2: Candidates
        
        On conversion to candidate:
        - Increment currentTerm
        - Vote for self
        - Reset election timer
        - Send RequestVote RPCs to all other servers
        """
        
        with self.lock:
            # 1. Increase the current term and vote for self
            self.raft_terms.current_term += 1
            self.raft_terms.voted_for = self.raft_terms.id  # FIXED: Vote for self, not hardcoded 1
            self.raft_terms.state = RaftState.candidate
            self._persist_state()
            
            print(f"[Node {self.raft_terms.id}] Became candidate for term {self.raft_terms.current_term}")
            
            #Construct the vote arguments
            vote_arguments = VoteArguments(
                current_term=self.raft_terms.current_term,
                candidate_id=self.raft_terms.id,
                last_log_index=self.raft_terms.last_log_index,
                last_log_term=self.raft_terms.last_log_term
            )
        
            #Vote for the node itself -> before sending out the RPC calls to the peers
            self.vote_count += 1
            self.received_votes = {self.raft_terms.id: True}  # Self voted
             
        #Store the reference of the thread / tasks to an array
        vote_request_threads = []
    
        # 3. Send RequestVote RPCs to all other servers in parallel
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.raft_terms.peers.items())) as vote_request_executor:
            for peer_id, peer_value in self.raft_terms.peers.items():
                
                if peer_id == self.raft_terms.id:
                    continue
                
                request_thread = vote_request_executor.submit(
                    self._send_vote_request_to_peer,
                    peer_id,
                    peer_value,
                    vote_arguments
                )
                
                vote_request_threads.append(request_thread)
            
             # Wait for all RPC threads to complete (2 second timeout)
            concurrent.futures.wait(vote_request_threads, timeout=2.0)
        
        with self.lock:
            
            total_servers = len(self.raft_terms.peers.items())
            majority_number = (total_servers // 2) + 1
            
            if self.vote_count >= majority_number and self.raft_terms.state == RaftState.candidate:
                self.raft_terms.state = RaftState.leader
                print(f"[Node {self.raft_terms.id}] ⭐ BECAME LEADER for term {self.raft_terms.current_term}")
                self._persist_state()
                self.send_health_checks()
            else:
                self.raft_terms.state = RaftState.follower
                print(f"[Node {self.raft_terms.id}] Lost election (only {self.vote_count} votes)")
                self.reset_election_timer()

        
    
    def handle_request_vote(self, vote_args: VoteArguments) -> bool:
        """
        PHASE 1: LEADER ELECTION - Receiver Implementation
        Raft Paper §5.1, §5.4 Receiver implementation for RequestVote RPC
        
        1. Reply false if term < currentTerm
        2. If votedFor is null or candidateId, and candidate's log is at 
           least as up-to-date as receiver's log, grant vote
        """
        
        with self.lock:
            print(f"[Node {self.raft_terms.id}] Received RequestVote from candidate {vote_args.candidate_id} for term {vote_args.current_term}")
            
            '''
            CHECK FOR THE FAILING CONDITIONS FIRST
            '''
            
            # Rule 1: Reply false if term < currentTerm
            if vote_args.current_term < self.raft_terms.current_term:
                print(f"[Node {self.raft_terms.id}] Rejecting vote: candidate term {vote_args.current_term} < current term {self.raft_terms.current_term}")
                return False
        
            # Rule 2: If votedFor is null (-1), check log recency
            if self.raft_terms.voted_for == -1 and self.raft_terms.last_log_index > vote_args.last_log_index:
                print(f"[Node {self.raft_terms.id}] Rejecting vote: candidate log not up-to-date")
                return False
            
            '''
            NOW IF ALL THE RULES ARE PASSED WE VOTE FOR THE CANDIDATE AND UPDATE OUR STATE
            '''
            print(f"[Node {self.raft_terms.id}] Received higher term {vote_args.current_term}, updating from {self.raft_terms.current_term}")
            self.raft_terms.current_term = vote_args.current_term
            self.raft_terms.voted_for = vote_args.candidate_id
            self.raft_terms.state = RaftState.follower
            persist_state = self._persist_state()
            
            #After the state is persisted -> reset the voted for variable -> read for the next election
            if persist_state:
                self.raft_terms.voted_for = -1
            
            # Rule 2: Reply false if term < currentTerm
            if vote_args.current_term < self.raft_terms.current_term:
                print(f"[Node {self.raft_terms.id}] Rejecting vote: candidate term {vote_args.current_term} < current term {self.raft_terms.current_term}")
                return False
            
            # Rule 3: If votedFor is null (-1) or candidateId, check log recency
            if self.raft_terms.voted_for == -1 or self.raft_terms.voted_for == vote_args.candidate_id:
                # Check if candidate's log is at least as up-to-date as receiver's log
                candidate_log_ok = self._is_log_up_to_date(
                    vote_args.last_log_term, 
                    vote_args.last_log_index
                )
                
                if candidate_log_ok:
                    # Grant vote and persist before responding
                    self.raft_terms.voted_for = vote_args.candidate_id
                    self._persist_state()
                    # Reset election timer when vote is granted (§5.2)
                    self.reset_election_timer()
                    print(f"[Node {self.raft_terms.id}] ✓ Granted vote to candidate {vote_args.candidate_id}")
                    return True
                else:
                    print(f"[Node {self.raft_terms.id}] Rejecting vote: candidate log not up-to-date")
                    return False
            
            print(f"[Node {self.raft_terms.id}] Rejecting vote: already voted for {self.raft_terms.voted_for}")
            return False

    def _send_vote_request_to_peer(self, peer_id, peer_value, vote_arguments):
        """Send RequestVote RPC to a peer (NO CALLBACK)"""
        conn = None
        try:
            print(f"[Node {self.raft_terms.id}] Sending RequestVote to Node {peer_id}")
            
            conn = rpyc.connect(
                peer_value["host"],
                peer_value["port"],
                config={"allow_public_attrs": True}
            )
            result = conn.root.exposed_send_vote_request(vote_arguments)
            
            print(f"[Node {self.raft_terms.id}] RPC to Node {peer_id}: {result}")
            
            # Update vote count if granted
            if result:
                with self.lock:
                    self.vote_count += 1
                    self.received_votes[peer_id] = True
        
        except Exception as e:
            print(f"[Node {self.raft_terms.id}] RPC to Node {peer_id} failed: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    # -----------------------------
    # Heartbeat / Log replication
    # -----------------------------
    
    
    def _hearbeat_ticker(self):
        """
        Daemon thread that sends periodic heartbeats (AppendEntries RPC)
        Only runs if node is leader
        Raft Paper §5.3: Leader sends heartbeats at least every 150ms
        """
        
        while not self.killed():
            
            # Only send heartbeats if leader
            if self.raft_terms.state == RaftState.leader:
                self.send_health_checks()
            
            self.heartbeat_timer_event.wait(timeout=0.1)
            self.heartbeat_timer_event.clear()
    
    def send_health_checks(self):
        
        """
        PHASE 2: LOG REPLICATION - Heartbeat
        Raft Paper §5.3: Leader sends AppendEntries RPC to all followers
        
        Contains log entries (or empty for heartbeat)
        Used to:
        1. Replicate logs to followers
        2. Detect down followers (timeout)
        3. Keep followers from starting elections (heartbeat resets timer)
        """
        
        if self.raft_terms.state != RaftState.leader:
            return
        
        with self.lock:
                            
                for peer_id, peer_value in self.raft_terms.peers.items():
                    
                    if peer_id == self.raft_terms.id:
                        continue
                    
                    prev_log_index = self.next_index[peer_id] - 1
                    prev_log_term = 0
                    
                    if prev_log_index >= 0 and prev_log_index < len(self.raft_terms.logs):
                        prev_log_term = self.raft_terms.logs[prev_log_index].get("term", 0)
                    
                    entries_to_send = self.raft_terms.logs[self.next_index[peer_id]:]
                    
                    health_checks_args = HealthCheckArguments(
                        current_term=self.raft_terms.current_term,
                        leader_id=self.raft_terms.id,
                        prev_log_index=prev_log_index,
                        prev_log_term=prev_log_term,
                        entries=entries_to_send,
                        leader_commit=self.raft_terms.commit_index
                    )
                    
                rpc_thread = threading.Thread(
                    target=self._send_health_checks_to_peer,
                    args=(peer_id, peer_value, health_checks_args),
                    daemon=True
                )
                            
                rpc_thread.start()

    
    def handle_health_check_request(self, health_check_arguments: HealthCheckArguments):
        
        """
        PHASE 2: LOG REPLICATION - Receiver Implementation
        Raft Paper §5.3: Receiver implementation for AppendEntries RPC
        
        1. Reply false if term < currentTerm
        2. Reply false if log doesn't contain entry at prevLogIndex with term = prevLogTerm
        3. If an existing entry conflicts, delete it and all following entries
        4. Append new entries not already in log
        5. If leaderCommit > commitIndex, set commitIndex = min(leaderCommit, last index)
        """
        with self.lock:
            # Rule 1: If higher term, become follower
            if health_check_arguments.current_term > self.raft_terms.current_term:
                self.raft_terms.state = RaftState.follower
                self.raft_terms.voted_for = -1
                self.raft_terms.current_term = health_check_arguments.current_term
                self._persist_state()
            
            # Rule 2: Reply false if term < currentTerm
            if health_check_arguments.current_term < self.raft_terms.current_term:
                return {"success": False, "term": self.raft_terms.current_term}
            
            # Reset election timer (heartbeat received)
            self.reset_election_timer()
            
            # Rule 3: Check log match at prevLogIndex
            if health_check_arguments.prev_log_index >= 0:
                
                # If we don't have this index, reject
                if health_check_arguments.prev_log_index >= len(self.raft_terms.logs):
                    print(f"[Node {self.raft_terms.id}] Log mismatch: missing index {health_check_arguments.prev_log_index}")
                    return {"success": False, "term": self.raft_terms.current_term}
            
                # Check if term matches
                if self.raft_terms.logs[health_check_arguments.prev_log_index].get("term", 0) != health_check_arguments.current_term:
                    print(f"[Node {self.raft_terms.id}] Log mismatch: term mismatch at index {health_check_arguments.prev_log_index}")
                    
                    # Delete conflicting entry and all following -> Get from the start till the previous index of the mismatched term
                    self.raft_terms.logs = self.raft_terms.logs[:health_check_arguments.prev_log_index]
                    return {"success": False, "term": self.raft_terms.current_term}
            
            # Rule 4: Append new entries
            if len(health_check_arguments.entries) > 0:
                
                self.raft_terms.logs = self.raft_terms.logs[:health_check_arguments.prev_log_index + 1]
                
                #Append new entries
                for entry in health_check_arguments.entries:
                    self.raft_terms.logs.append(entry)
                
                #Update last_log_index and log_term
                self.raft_terms.last_log_index = len(self.raft_terms.logs) - 1
                self.raft_terms.last_log_term = self.raft_terms.logs[-1].get("term", 0)
                
                print(f"[Node {self.raft_terms.id}] Appended {len(health_check_arguments.entries)} entries, now at index {self.raft_terms.last_log_index}")
            
            #Rule 5: Advance commit index
            if health_check_arguments.leader_commit > self.raft_terms.commit_index:
                old_commit = self.raft_terms.commit_index
                self.raft_terms.commit_index = min(health_check_arguments.leader_commit, len(self.raft_terms.logs - 1)) #len(self.raft_terms.logs - 1) this will be updated since we have done the append entries on rule 4
                print(f"[Node {self.raft_terms.id}] Advanced commitIndex from {old_commit} to {self.raft_terms.commit_index}")
                # TODO: Apply committed entries to state machine
            
            return {"success": True, "term": self.raft_terms.current_term}
        
    '''
    HELPER FUNCTION FOR LEADER ELECTION
    '''
    def _send_health_checks_to_peer(self, peer_id: int, peer_value: str, health_check_args: HealthCheckArguments):
        
        """
        Send AppendEntries RPC to a peer
        Raft Paper §5.3: Receiver implementation
        
        If follower rejects (log doesn't match):
        - Decrement nextIndex[peer]
        - Retry with earlier log entries
        
        If follower accepts:
        - Update matchIndex[peer] and nextIndex[peer]
        """
        
        conn = None
        
        try:
            print(f"[Node {self.raft_terms.id}] Sending health checks to Node {peer_id}")
            
            conn = rpyc.connect(
                peer_value["host"],
                peer_value["port"],
                config={"allow_public_attrs": True}
            )
            
            result = conn.root.exposed_send_health_check_request(health_check_args)
            
            print(f"[Node {self.raft_terms.id}] RPC to Node {peer_id}: {result}")
            
            with self.lock:
                
                if result is None:
                    return

                if result.get("term", 0) > self.raft_terms.current_term:
                    self.raft_terms.current_term = result["term"]
                    self.raft_terms.state = RaftState.follower
                    self.raft_terms.voted_for = -1
                    return 

                # If success=False: follower's log doesn't match
                if not result.get("success", False):
                    # Decrement nextIndex[peer] and retry next time
                    if self.next_index[peer_id] > 0:
                        self.next_index[peer_id] -= 1
                        print(f"[Node {self.raft_terms.id}] Log mismatch with Node {peer_id}, decrement nextIndex to {self.next_index[peer_id]}")

                    return

                #If success=True: follower accepted the entries
                # Update matchIndex and nextIndex for this peer
                new_match_index = health_check_args.prev_log_index + len(health_check_args.entries)
                self.match_index[peer_id] = new_match_index
                self.next_index[peer_id] = new_match_index + 1
                
                print(f"[Node {self.raft_terms.id}] Node {peer_id} now has logs up to index {new_match_index}")
                
                # Check if we can advance commitIndex
                # commitIndex = highest index replicated on majority
                self._try_advance_commit_index()
            
        except Exception as e:
            # Peer is down or unreachable - do nothing
            # Retry happens on next heartbeat cycle (100ms later)
            print(f"[Node {self.raft_terms.id}] Heartbeat to Node {peer_id} failed: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def _try_advance_commit_index(self):
        
        """
        LEADER ONLY: Check if we can advance commitIndex
        commitIndex = highest index replicated on majority of servers
        Raft Paper §5.3
        """
        
        if self.raft_terms.state == RaftState.leader:
            return

        # Count how many servers have replicated each log index
        
        for index in range(len(self.raft_terms.logs) - 1, self.raft_terms.commit_index, -1):
            
            replicated_count = 1 #To count in self
            
            for peer_id in self.raft_terms.peers.keys():
                if peer_id == self.raft_terms.id:
                    continue
                    
                if self.match_index.get(peer_id, 0) >= index:
                    replicated_count += 1
            
            total_servers = len(self.raft_terms.peers)
            majority = (total_servers // 2) + 1
            
            if replicated_count >= majority and self.raft_terms.logs[index].get("term") == self.raft_terms.current_term:
                self.raft_terms.commit_index = index
                print(f"[Node {self.raft_terms.id}] Advanced commitIndex to {index}")
                # TODO: Apply committed entries to state machine
                break
            
            
    def _send_vote_request_to_peer(self, peer_id, peer_value, vote_arguments):
        """Send RequestVote RPC to a peer (NO CALLBACK)"""
        conn = None
        try:
            print(f"[Node {self.raft_terms.id}] Sending RequestVote to Node {peer_id}")
            
            conn = rpyc.connect(
                peer_value["host"],
                peer_value["port"],
                config={"allow_public_attrs": True}
            )
            result = conn.root.exposed_send_vote_request(vote_arguments)
            
            print(f"[Node {self.raft_terms.id}] RPC to Node {peer_id}: {result}")
            
            # Update vote count if granted
            if result:
                with self.lock:
                    self.vote_count += 1
                    self.received_votes[peer_id] = True
        
        except Exception as e:
            print(f"[Node {self.raft_terms.id}] RPC to Node {peer_id} failed: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def _is_log_up_to_date(self, candidate_last_term: int, candidate_last_index: int) -> bool:
        """
        ADDED: Check if candidate's log is at least as up-to-date as receiver's log
        Raft Paper §5.4.1: Comparing logs by (lastLogTerm, lastLogIndex)
        """
        receiver_last_term = self.raft_terms.last_log_term
        receiver_last_index = self.raft_terms.last_log_index
        
        # If last terms differ, higher term is more up-to-date
        if candidate_last_term != receiver_last_term:
            return candidate_last_term > receiver_last_term
        
        # If last terms are same, higher index is more up-to-date
        return candidate_last_index >= receiver_last_index
    
    def _persist_state(self):
        
        """
        Persist currentTerm and votedFor to disk before responding to RPCs
        Raft Paper: "Persistent state (updated on stable storage before responding to RPCs)"
        
        Simple append-only log format (one JSON object per line) -> id, current_term, voted_for
        """
        
        try:
            with open(self.raft_terms.logs_file_path, 'a') as source_file:
                state_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "node_id": self.raft_terms.id,
                    "current_term": self.raft_terms.current_term,
                    "state": self.raft_terms.state.name
                }
                source_file.write(json.dumps(state_entry) + '\n')
        
        except Exception as e:
            print(f"[Node {self.raft_terms.id}] Error persisting state: {e}")
            return -1
    
    def _load_persistent_state(self):
        """
        Docstring for _load_persistent_state
        
        :param self: Description
        Load persistent state (current_term, voted_for) when the server is boot up / restarted
        Reads the last entry from the logs to recover the state
        """
        
        try:
            
            with open(self.raft_terms.logs_file_path, 'r') as f:
                lines = f.readlines()
                
                if lines:
                    last_entry = json.loads(lines[-1])
                    self.raft_terms.current_term = last_entry.get('current_term', 0)
                    self.raft_terms.voted_for = last_entry.get('voted_for', -1)
                    print(f"[Node {self.raft_terms.id}] Recovered state: term={self.raft_terms.current_term}, voted_for={self.raft_terms.voted_for}")
        
        except FileNotFoundError:
            # First startup - file doesn't exist yet
            print(f"[Node {self.raft_terms.id}] No persistent state found, starting fresh")
            
        except Exception as e:
            print(f"[Node {self.raft_terms.id}] Error loading persistent state: {e}")
        
    
    def killed(self):
        # A simple check for a killed state (using a lock might be safer in real code)
        return self._killed
    
    def kill(self):
        # A simple check for a killing a node
        self._killed = True
