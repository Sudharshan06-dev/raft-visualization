# RAFT-Based Distributed Key-Value Store with Real-Time Visualization

## 🎯 Project Overview

A **production-ready distributed database** combining:
- **RAFT Consensus Algorithm** - Ensures all nodes stay in sync
- **Timestamped In-Memory KV Store** - Stores versioned data with TTL
- **Real-Time Visualization** - Animate leader election, log replication, and data distribution

**What it does:**
```
User writes: SET user:1 name=Alice
    ↓
RAFT Leader accepts write
    ↓
Animates: Leader sends to 4 followers
    ↓
Animates: Followers acknowledge replication
    ↓
All nodes apply: state_machine["user:1"]["name"] = "Alice" @ timestamp T
    ↓
User reads: GET user:1 name (at any timestamp)
    ↓
Returns: Alice (from replicated state, guaranteed consistent)
```

**Current Status:** ✅ RAFT Core + KV Store | 🚧 Visualization (React Dashboard)

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              React Web Dashboard (Visualization)            │
│  • Real-time node status (Leader/Follower/Candidate)       │
│  • Animated RPC messages between nodes                     │
│  • Log entry replication animation                         │
│  • Data distribution across cluster                        │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket
        ┌──────────┬───────────┼───────────┬──────────┐
        │          │           │           │          │
    ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼──┐
    │ Node │  │ Node │  │ Node │  │ Node │  │ Node │
    │  A   │  │  B   │  │  C   │  │  D   │  │  E   │
    │LEADER│  │FOLWR │  │FOLWR │  │FOLWR │  │FOLWR │
    └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘  └──┬───┘
       │         │         │         │         │
       └─────────┼─────────┼─────────┼─────────┘
                 │
          ┌──────▼──────────────┐
          │  Consensus Layer    │
          │  (RAFT Protocol)    │
          │  • Leader Election  │
          │  • Log Replication  │
          │  • Term Management  │
          └──────┬──────────────┘
                 │
          ┌──────▼──────────────┐
          │   Replication Log   │
          │ (Identical on all)  │
          │ ┌─────────────────┐ │
          │ │ {index:0, ...}  │ │
          │ │ {index:1, ...}  │ │
          │ │ {index:2, ...}  │ │
          │ └─────────────────┘ │
          └──────┬──────────────┘
                 │
          ┌──────▼──────────────────────┐
          │  Key-Value State Machine    │
          │  (Applied entries)          │
          │  ┌─────────────────────┐    │
          │  │ user:1 {name:Alice} │    │
          │  │ user:2 {name:Bob}   │    │
          │  │ order:1 {value:100} │    │
          │  └─────────────────────┘    │
          │  (Identical on all nodes)   │
          └─────────────────────────────┘
```

---

## 📁 Project Structure

```
project/
├── RAFT Consensus Layer
│   ├── raft_server.py              # Core RAFT implementation (500+ lines)
│   ├── raft_rpc.py                 # RPC service exposing methods
│   ├── raft_structure.py           # RAFT state management
│   ├── raft_state.py               # Enum: Leader/Follower/Candidate
│   ├── vote_arguments.py           # RequestVote RPC payload
│   ├── health_check_arguments.py   # AppendEntries RPC payload
│   └── IRaftActions.py             # Abstract interface
│
├── Key-Value Store Layer
│   ├── byte_data_db.py             # KV store singleton (timestamped)
│   ├── byte_data_record.py         # Record container (fields)
│   ├── byte_data_field.py          # Scalar field (with TTL)
│   ├── byte_data_list_field.py     # List field (with TTL)
│   ├── byte_data_search.py         # Scan/search operations
│   ├── byte_data_backup_restore.py # Snapshots & restore
│   └── IByteDataField.py           # Field interface
│
├── Cluster Management
│   ├── start_cluster.py            # Start 5-node cluster
│   ├── test_consensus.py           # Test RAFT consensus
│   └── test_kv_store.py            # Test KV operations
│
└── Visualization (Coming Soon)
    ├── frontend/
    │   ├── dashboard.jsx           # Main dashboard
    │   ├── nodes.jsx               # Node status cards
    │   ├── animation.jsx           # RPC animations
    │   └── index.html              # HTML entry point
    └── websocket_server.py         # Push updates to frontend
```

---

## 🔑 Key Concepts Explained

### **1. RAFT Consensus (Distributed Agreement)**

**The Problem:**
```
5 nodes, client writes to each independently
Node A: SET x=100
Node B: SET x=200  ← Different value!
Node C: SET x=100
Result: Inconsistent data → application breaks
```

**The Solution (RAFT):**
```
1. Leader elected (Node A wins)
2. Client writes to Node A only
3. Node A replicates to all followers (B, C, D, E)
4. When majority (3/5) acknowledge: commit
5. All 5 nodes apply: SET x=100
Result: Guaranteed consistency ✅
```

### **2. Timestamped Key-Value Store**

**The Concept:**
```python
# Normal KV: current value only
store["user:1"]["name"] = "Alice"

# Timestamped KV: entire history
store["user:1"]["name"] = [
    {value: "Alice", timestamp: 1000, ttl: None},      # Created at T1000
    {value: "Bob", timestamp: 2000, ttl: None},         # Changed at T2000
    {value: "Charlie", timestamp: 3000, ttl: 300},      # Changed at T3000, expires at T3300
]

# Read at T1500: returns "Alice"
# Read at T2500: returns "Bob"
# Read at T3100: returns "Charlie"
# Read at T3500: not found (expired!)
```

**Why it matters:**
- Read historical data at any point in time
- Automatic expiration (TTL)
- Temporal queries (what was the value at T?)

### **3. Log Replication (RAFT Phase 2)**

**How data flows:**
```
┌─────────────┐
│Client Write │  "SET user:1 name=Alice"
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ Leader (Node A)                                  │
│ 1. Append to log: {index:0, term:1, cmd:"SET..."}
│ 2. Persist to disk                              │
│ 3. Send AppendEntries RPC to all followers      │
└──────┬──────────────────────────────────────────┘
       │
    ┌──┴──┬──────┬──────┬──────┐
    │     │      │      │      │
    ▼     ▼      ▼      ▼      ▼
 ┌──────────────────────────────────────┐
 │ Followers (Nodes B, C, D, E)         │
 │ 1. Receive AppendEntries             │
 │ 2. Check log matching (prevLogIndex) │
 │ 3. Append entry to log               │
 │ 4. Return success=True               │
 └──────────────────────────────────────┘
    │     │      │      │      │
    └──┬──┴──┬───┴──┬───┴──┬───┘
       │     │      │      │
       ▼     ▼      ▼      ▼
┌──────────────────────────────────────────┐
│ Leader Counts Replications               │
│ Received ACK from: A, B, C (3/5)         │
│ Majority? YES (3 >= 3)                   │
│ → Advance commitIndex                    │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Apply to State Machine                   │
│ Execute: SET user:1 name=Alice           │
│ At timestamp: 1000                       │
│ In KV store: state_machine["user:1"] = { │
│     "name": {                            │
│         "value": "Alice",                │
│         "timestamp": 1000,               │
│         "ttl": None                      │
│     }                                    │
│ }                                        │
└──────────────────────────────────────────┘
```

### **4. Thread Safety (Preventing Race Conditions)**

**Without locks (DANGER!):**
```python
Thread 1: reads term = 5
Thread 2: reads term = 5
Thread 1: increments to 6, writes
Thread 2: increments to 6, writes (WRONG! Should be 7)
Result: Term stuck at 6, leader election broken ❌
```

**With locks (SAFE):**
```python
with self.lock:
    term = 5
    term += 1           # Only one thread here at a time
    write(term)         # Safe!
Result: Term correctly becomes 6 ✅
```

### **5. ThreadPoolExecutor (Parallel Message Sending)**

**Without ThreadPoolExecutor (SLOW):**
```python
Send to Node B: wait 100ms
Send to Node C: wait 100ms
Send to Node D: wait 100ms
Send to Node E: wait 100ms
Total: 400ms ⏳
```

**With ThreadPoolExecutor (FAST):**
```python
Send to Node B: 100ms \
Send to Node C: 100ms  } All in parallel
Send to Node D: 100ms  /
Send to Node E: 100ms /
Total: 100ms ⚡
```

---

## 🎬 Visualization (Real-Time Animation)

### **What Gets Animated:**

**1. Leader Election:**
```
┌─────────────────────────────────────────────┐
│ ANIMATION: Election starts                  │
├─────────────────────────────────────────────┤
│ Node A (CANDIDATE) ──RequestVote──> Node B  │
│ Node A (CANDIDATE) ──RequestVote──> Node C  │
│ Node A (CANDIDATE) ──RequestVote──> Node D  │
│ Node A (CANDIDATE) ──RequestVote──> Node E  │
│                                             │
│ Node B ──True──> Node A                     │
│ Node C ──True──> Node A                     │
│ Node D ──True──> Node A                     │
│ Node E ──True──> Node A                     │
│                                             │
│ Node A becomes LEADER ⭐                    |
└─────────────────────────────────────────────┘
```

**2. Log Replication:**
```
┌─────────────────────────────────────────────┐
│ ANIMATION: Append entry to all              │
├─────────────────────────────────────────────┤
│ Node A (LEADER) ──AppendEntries──> Node B   │
│ Node A (LEADER) ──AppendEntries──> Node C   │
│ Node A (LEADER) ──AppendEntries──> Node D   │
│ Node A (LEADER) ──AppendEntries──> Node E   │
│                                             │
│ Nodes B, C, D, E update their logs          │
│                                             │
│ Node B ──Success──> Node A                  │
│ Node C ──Success──> Node A                  │
│ Node D ──Success──> Node A                  │
│ Node E ──Success──> Node A                  │
│                                             │
│ Node A: 5/5 nodes have entry ✅              │
│ All nodes: Apply to state machine ✅         │
└─────────────────────────────────────────────┘
```

**3. Node Status Cards:**
```
┌─────────────┬─────────────┬─────────────┐
│   NODE A    │   NODE B    │   NODE C    │
├─────────────┼─────────────┼─────────────┤
│ LEADER ⭐  │ FOLLOWER ✓  │ FOLLOWER ✓   |
│ Term: 1     │ Term: 1     │ Term: 1     │
│ Logs: 5     │ Logs: 5     │ Logs: 5     │
│ Commit: 4   │ Commit: 4   │ Commit: 4   │
└─────────────┴─────────────┴─────────────┘
```

---

## 🚀 Running the System (YET TO IMPLEMENT)

### **Start 5-Node Cluster**
```bash
python start_cluster.py
```

Output:
```
[Cluster] Starting 5-node RAFT cluster...
[Node A] RPyC Server listening on 127.0.0.1:5001
[Node B] RPyC Server listening on 127.0.0.1:5002
[Node C] RPyC Server listening on 127.0.0.1:5003
[Node D] RPyC Server listening on 127.0.0.1:5004
[Node E] RPyC Server listening on 127.0.0.1:5005

[Node C] Election timeout! Starting election...
[Node C] Became candidate for term 1
[Node A] Received RequestVote from C for term 1
[Node B] Received RequestVote from C for term 1
[Node D] Received RequestVote from C for term 1
[Node E] Received RequestVote from C for term 1

[Node A] ✓ Granted vote to C
[Node B] ✓ Granted vote to C
[Node D] ✓ Granted vote to C
[Node E] ✓ Granted vote to C

✨ Node C elected as LEADER in term 1

[Cluster] Starting WebSocket server on 127.0.0.1:8000...
[Frontend] Open http://localhost:3000 to visualize
```
---

## 🚨 Important Notes

### **Read Consistency Guarantees**

**Strong Consistency (Leader):**
```python
# Leader can serve both committed and uncommitted reads
result = leader.exposed_read_log(key, field)
# Safe: leader always has latest
```

**Eventual Consistency (Followers):**
```python
# Followers only serve committed entries
result = follower.exposed_read_log(key, field)
# If entry not committed yet: "not_committed_yet"
# Wait for next heartbeat, then try again
```

### **Known Limitations**

❌ **No log compaction yet** (Phase 3)
- Logs grow unbounded in memory
- Will add snapshots later

❌ **Single-threaded operations**
- Commands execute sequentially
- Will add batch processing in optimization phase

❌ **No persistence between restarts** (yet)
- Need to implement WAL for logs
- Currently only persist term/votedFor

---

## 🎬 Next Steps

### **Phase 3: Log Compaction**
- Implement snapshotting
- Add bloom filters for search efficiency
- Garbage collect old logs

### **Phase 4: Visualization**
- React dashboard
- WebSocket push updates
- Animated RPC messages
- Real-time node status

### **Phase 5: Optimization**
- Batch write operations
- Index management (for fast scans)
- Cluster configuration changes
- Load balancing

---

## 📚 Resources

- **RAFT Paper**: https://raft.github.io/raft.pdf
- **Visualization**: http://thesecretlivesofdata.com/raft/
- **In-Memory DB Patterns**: https://redis.io/docs/

---