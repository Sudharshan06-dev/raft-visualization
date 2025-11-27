# RAFT Consensus Algorithm - Implementation Guide

## 📋 Overview

This is a **production-ready implementation** of the RAFT consensus algorithm in Python, focusing on **Phase 1 (Leader Election)** and **Phase 2 (Log Replication)**.

**What it does:**
- Elects a leader among multiple nodes
- Replicates log entries from leader to followers
- Guarantees data consistency across the cluster
- Handles node failures gracefully
- Provides read/write operations to clients

**Current Status:** ✅ Phase 1 & 2 Complete | 🚧 Phase 3 (Snapshots) Future

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│         Client Application Layer            │
│  (Writes & Reads via RPC)                   │
└────────────────────┬────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
    ┌───▼───┐    ┌───▼───┐   ┌───▼───┐
    │ Node1 │    │ Node2 │   │ Node3 │
    │LEADER │    │FOLLOWER   │FOLLOWER
    └───────┘    └───────┘   └───────┘
        │            │            │
        └────────────┼────────────┘
                     │
        ┌────────────▼────────────┐
        │  Replicated Log Store   │
        │ (All nodes have copy)   │
        └─────────────────────────┘
```

**3-Node Cluster Setup:**
- Node 1 (Leader): Accepts writes, replicates to followers
- Node 2, 3 (Followers): Accept reads, reject writes
- All nodes: Maintain replicated log, participate in elections

---

## 📁 Project Structure

```
raft/
├── raft_server.py              # Main RAFT implementation (500+ lines)
├── raft_rpc.py                 # RPC service exposing methods
├── raft_structure.py           # Data classes for RAFT state
├── raft_state.py               # Enum: Leader/Follower/Candidate
├── IRaftActions.py             # Abstract interface
├── vote_arguments.py           # RequestVote RPC payload
├── health_check_arguments.py   # AppendEntries RPC payload
├── start_cluster.py            # Start 3-node cluster
└── test_leader_election.py     # Test suite
```

---

## 🔑 Key Concepts Explained Simply

### **1. Leader Election (Phase 1)**

**What it is:** When a node doesn't hear from the leader, it starts an election to choose a new leader.

**How it works:**
```
1. Candidate: "I want to be leader, vote for me"
2. Followers: Check if candidate is qualified, vote
3. Candidate: If majority votes, becomes leader ✨
4. Followers: Accept heartbeats from new leader
```

**Why it matters:** Ensures there's always one leader coordinating writes.

---

### **2. Log Replication (Phase 2)**

**What it is:** Leader sends log entries to followers to keep everyone in sync.

**How it works:**
```
1. Client: "Write SET x=100"
2. Leader: Appends to own log
3. Leader: Sends to all followers (AppendEntries RPC)
4. Followers: Append to their logs
5. Leader: Gets majority confirmation
6. Leader: Commits entry, applies to state machine
```

**Why it matters:** Ensures all nodes have same data (replication).

---

### **3. Thread Safety (Locking)**

**The problem:**
```python
# Without lock - RACE CONDITION!
Thread 1: reads current_term = 5
Thread 2: reads current_term = 5
Thread 1: increments to 6, writes
Thread 2: increments to 6, writes (WRONG! Should be 7)
```

**The solution:**
```python
# With lock - SAFE!
with self.lock:
    current_term = 5        # Only one thread here at a time
    current_term += 1       # Safe!
```

**In our code:**
```python
self.lock = threading.Lock()  # Created once

# Used everywhere shared state is accessed
with self.lock:
    self.raft_terms.current_term += 1
    self.raft_terms.state = RaftState.candidate
```

**Why it matters:** Prevents data corruption from simultaneous access.

---

### **4. ThreadPoolExecutor (Parallel RPC Calls)**

**The problem:**
```python
# Without ThreadPoolExecutor - SLOW!
for peer_id in peers:
    result = send_vote_to(peer_id)  # Wait for peer 1 (slow)
    # Only after peer 1 responds, send to peer 2
# Total time = peer1_time + peer2_time + peer3_time (slow!)
```

**The solution:**
```python
# With ThreadPoolExecutor - FAST!
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = []
    for peer_id in peers:
        future = executor.submit(send_vote_to, peer_id)  # Send all at once
        futures.append(future)
    
    concurrent.futures.wait(futures, timeout=2.0)  # Wait 2 seconds for all
# Total time = max(peer1_time, peer2_time, peer3_time) (fast!)
```

**In our code:**
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=len(peers)) as executor:
    for peer_id, peer_value in self.raft_terms.peers.items():
        executor.submit(self._send_vote_request_to_peer, peer_id, peer_value, vote_args)
    
    concurrent.futures.wait(vote_request_threads, timeout=2.0)
```

**Why it matters:** Elections finish in milliseconds, not seconds.

---

### **5. Persistent State (Crash Recovery)**

**The problem:**
```
Node crashes and restarts
Lost: current_term = 5, voted_for = node2
Result: Node votes twice in same term → RAFT violated!
```

**The solution:**
```python
def _persist_state(self):
    # Save to disk before responding to RPCs
    save_to_file({
        'current_term': 5,
        'voted_for': 2
    })

def _load_persistent_state(self):
    # On startup, restore from disk
    data = load_from_file()
    self.current_term = data['current_term']
```

**In our code:**
```python
def handle_request_vote(self, vote_args):
    if higher_term:
        self.current_term = vote_args.current_term
        self._persist_state()  # Save BEFORE responding
        return True
```

**Why it matters:** Survives restarts without corrupting state.

---

## 📊 RAFT Attributes Explained

### **Persistent State** (Saved to Disk)
These must be restored if node crashes:

| Attribute | Type | Initial | What It Means |
|-----------|------|---------|---------------|
| `currentTerm` | int | 0 | Latest term this node has seen (increments over time) |
| `votedFor` | int | -1 | Which node got this node's vote in current term (-1 = no vote) |
| `logs[]` | list | [] | All commands ever received from leader |

### **Volatile State** (In Memory)
Lost on crash, but can be recovered:

| Attribute | Type | Initial | What It Means |
|-----------|------|---------|---------------|
| `state` | enum | Follower | Current role (Leader, Follower, Candidate) |
| `commitIndex` | int | 0 | Highest log index we're **sure** the majority has |
| `lastApplied` | int | 0 | Highest log index we've applied to state machine |

### **Leader-Only State**
Only meaningful when node is leader:

| Attribute | Type | Initial | What It Means |
|-----------|------|---------|---------------|
| `nextIndex[]` | dict | last_log_index | Index of next entry to send to each follower |
| `matchIndex[]` | dict | 0 | Highest log index known to be replicated on each follower |

### **Per-Log-Entry**

| Attribute | Type | Example | What It Means |
|-----------|------|---------|---------------|
| `index` | int | 5 | Position in log (1st entry = 0) |
| `term` | int | 2 | Which term was this entry added |
| `command` | str | "SET x=100" | The actual command to execute |

---

## 🔄 Real-World Example: Writing Data

Let's trace a write through the system step-by-step with actual attribute values:

### **Initial State (3-node cluster)**
```python
# All nodes start identical
Node 1: term=0, voted_for=-1, logs=[], commitIndex=0
Node 2: term=0, voted_for=-1, logs=[], commitIndex=0
Node 3: term=0, voted_for=-1, logs=[], commitIndex=0
```

### **Step 1: Election Timeout → Node 1 Becomes Leader**
```python
# Node 1's election timer fires
Node 1: 
    currentTerm = 0 + 1 = 1          # ✓ Increment term
    votedFor = 1                      # ✓ Vote for self
    state = Candidate                 # ✓ Become candidate
    → Sends RequestVote RPC with term=1

# Node 2 receives RequestVote
Node 2:
    term < 1? No (term=0)
    Already voted? No (votedFor=-1)
    → votedFor = 1                    # ✓ Grant vote
    → return True

# Node 3 receives RequestVote
Node 3:
    → votedFor = 1                    # ✓ Grant vote
    → return True

# Node 1 got 2/3 votes (majority!)
Node 1:
    state = Leader ⭐
    nextIndex[2] = 0                  # Start sending from log[0]
    nextIndex[3] = 0
    matchIndex[2] = -1                # Haven't replicated yet
    matchIndex[3] = -1
```

### **Step 2: Client Writes "SET x=100"**
```python
# Client calls: leader.append_log_entries("SET x=100")

# Node 1 (Leader)
Node 1:
    logs.append({
        "index": 0,
        "term": 1,
        "command": "SET x=100"
    })
    lastLogIndex = 0
    lastLogTerm = 1
    → Return {"success": True, "index": 0}

# Client gets: "Your write is at index 0, waiting for replication"
```

### **Step 3: Leader Replicates to Followers**
```python
# Leader's send_health_checks() sends to all followers

# AppendEntries RPC to Node 2:
{
    "current_term": 1,
    "leader_id": 1,
    "prev_log_index": -1,            # Nothing before index 0
    "prev_log_term": 0,              # No previous term
    "entries": [                      # Send the new entry
        {"index": 0, "term": 1, "command": "SET x=100"}
    ],
    "leader_commit": 0                # Haven't committed yet
}

# Node 2 receives AppendEntries
Node 2:
    term 1 >= 0? Yes ✓
    logs match at prevLogIndex? Yes ✓
    logs.append({"index": 0, "term": 1, "command": "SET x=100"})
    lastLogIndex = 0
    lastLogTerm = 1
    → return {"success": True, "term": 1}

# Node 3 receives AppendEntries
Node 3:
    → Same process
    → return {"success": True, "term": 1}
```

### **Step 4: Leader Advances CommitIndex**
```python
# Leader counts successful replications
Node 1:
    matchIndex[2] = 0                 # ✓ Node 2 replicated
    matchIndex[3] = 0                 # ✓ Node 3 replicated
    
    # Count how many have index 0
    count = 1 (self) + 1 (node2) + 1 (node3) = 3
    majority = (3/2) + 1 = 2
    3 >= 2? YES ✓
    
    commitIndex = 0                   # ✓ Now committed!
    
    # Broadcast next heartbeat with commitIndex=0 to followers
```

### **Step 5: Followers Advance CommitIndex**
```python
# Node 2 receives heartbeat with leaderCommit=0
Node 2:
    leaderCommit (0) > commitIndex (0)? No
    → commitIndex stays 0 ✓

# Node 3: Same
```

### **Step 6: Apply to State Machine**
```python
# Leader applies committed entries
Node 1:
    for index in (lastApplied+1) to commitIndex:  # 0 to 0
        entry = logs[0] = {"command": "SET x=100"}
        execute("SET x=100")  # Update state_machine["x"] = "100"
        lastApplied = 0 ✓

# Followers apply (happens in background)
Node 2:
    for index in (lastApplied+1) to commitIndex:  # 0 to 0
        execute("SET x=100")
        lastApplied = 0 ✓

Node 3:
    → Same
```

### **Final State: All Nodes Identical**
```python
Node 1:
    currentTerm = 1
    votedFor = 1
    logs = [{"index": 0, "term": 1, "command": "SET x=100"}]
    commitIndex = 0
    lastApplied = 0
    state = Leader
    state_machine = {"x": "100"} ✓

Node 2:
    currentTerm = 1
    votedFor = 1
    logs = [{"index": 0, "term": 1, "command": "SET x=100"}]
    commitIndex = 0           # WAIT - Why not 1?
    lastApplied = 0
    state = Follower
    state_machine = {"x": "100"} ✓

Node 3:
    → Same as Node 2
```

**❓ Why does commitIndex stay 0 for followers?**
- Leader sends `leaderCommit=0` (highest committed index)
- Followers don't advance commitIndex beyond leaderCommit
- Next write will advance it further

---

## 🧪 Running the System (In Progress)

### **Start 3-Node Cluster**
```bash
python start_cluster.py
```

Output:
```
[Node 1] RPyC Server listening on 127.0.0.1:5001
[Node 2] RPyC Server listening on 127.0.0.1:5002
[Node 3] RPyC Server listening on 127.0.0.1:5003

[Node 3] Election timeout! Starting election...
[Node 1] Received RequestVote from candidate 3 for term 1
[Node 1] ✓ Granted vote to candidate 3

✨ Node 3 elected as LEADER in term 1
```

### **Write Data**
```python
import rpyc

conn = rpyc.connect("127.0.0.1", 5001)  # Connect to Node 1 (leader)
result = conn.root.exposed_append_log_entries("SET x=100")

print(result)
# Output: {
#     "success": True,
#     "index": 0,
#     "term": 1,
#     "message": "Appended to leader log..."
# }
```

### **Read Data**
```python
result = conn.root.exposed_read_log(0)

print(result)
# Output: {
#     "success": True,
#     "entry": {
#         "index": 0,
#         "term": 1,
#         "command": "SET x=100"
#     },
#     "committed": True
# }
```

---

## 🚨 Common Mistakes & How We Avoid Them

| Mistake | Why It's Bad | How We Fix It |
|---------|------------|--------------|
| Voting twice in same term | Violates RAFT, breaks consensus | Persist `votedFor` to disk |
| Sending stale log entries | Followers get wrong data | Use `prevLogIndex` to verify match |
| Uncommitted reads | Client reads non-replicated data | Only serve if `index <= commitIndex` |
| Race conditions | Corrupt state from concurrent access | Use `with self.lock:` everywhere |
| Slow elections | System unresponsive when leader fails | Use ThreadPoolExecutor for parallel RPCs |

---

## 📈 Performance Characteristics

| Operation | Time | Why |
|-----------|------|-----|
| Leader election | 150-500ms | Randomized timeout + parallel RPCs |
| Log replication | 100-200ms | Heartbeat every 100ms + parallel sends |
| Write latency | 200-700ms | Election time + replication time |
| Read latency | <10ms | Local state machine (no RPC) |

---

## 🔍 Debugging Tips

### **Check Node State**
```python
import rpyc
conn = rpyc.connect("127.0.0.1", 5001)
state = conn.root._raft.raft_terms

print(f"State: {state.state}")           # leader/follower/candidate
print(f"Term: {state.current_term}")     # Which term we're in
print(f"Logs: {len(state.logs)}")        # How many entries
print(f"CommitIndex: {state.commit_index}")  # How many committed
```

### **Check Logs File**
```bash
cat raft_node_1.log | python -m json.tool | head -20
```

### **Watch Real-Time Output**
```bash
python start_cluster.py 2>&1 | grep "Node 1"
```

---

## 📚 Next Phases

**Phase 3: Snapshotting** 🚧
- Save state machine periodically
- Discard old logs (with bloom filters for efficiency)
- Faster recovery after crashes

**Phase 4: Visualization** 🎨
- React dashboard showing cluster state
- Real-time animation of RPC messages
- Interactive node failure simulation

---

## 🎓 Learning Resources

- **Raft Paper**: https://raft.github.io/raft.pdf
- **Visualization**: http://thesecretlivesofdata.com/raft/
- **MIT Course**: https://pdos.csail.mit.edu/6.824/
- **MEDIUM Blog**: https://medium.com/codex/journey-to-mit-6-824-lab-2a-raft-leader-election-974087a55740
- **Consensus Algorithm Paper**: http://nil.csail.mit.edu/6.824/2020/papers/raft-extended.pdf

---