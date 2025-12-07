import threading
import time
import rpyc
from raft.raft_server import Raft
from raft.raft_rpc import RaftService, ThreadedServer
from inmem.byte_data_db import ByteDataDB
from inmem.state_machine_applier import StateMachineApplier

# Configuration for 3-node cluster
CLUSTER_CONFIG = {
    "A": {"host": "127.0.0.1", "port": 5001},
    "B": {"host": "127.0.0.1", "port": 5002},
    "C": {"host": "127.0.0.1", "port": 5003},
}

class RaftCluster:
    """Helper class to manage RAFT cluster startup"""
    
    def __init__(self, config):
        self.config = config
        self.servers = {}
        self.nodes = {}
    
    def start_node(self, node_id, start_timers=False):  # ← Add parameter with default False
        """Start a single RAFT node with RPC server"""
        print(f"\n[Cluster] Starting Node {node_id}...")
        
        db = ByteDataDB.get_instance()
        applier = StateMachineApplier(db)
        
        # Create the Raft node
        peers_config = {
            nid: cfg for nid, cfg in self.config.items() if nid != node_id
        }
        
        raft_node = Raft(
            node_id=node_id,
            peers_config=peers_config,
            logs_file_path=f"raft_node_{node_id}.jsonl",
            state_machine_applier=applier
        )
        
        # Create RPC service
        service = RaftService(raft_node, db)
        
        node_config = self.config[node_id]
        server = ThreadedServer(
            service,
            hostname=node_config["host"],
            port=node_config["port"],
        )
        
        print(f"[Node {node_id}] RPC server listening on {node_config['host']}:{node_config['port']}")
        
        # Store references BEFORE starting threads
        self.servers[node_id] = server
        self.nodes[node_id] = raft_node
        
        # Run server in background thread
        server_thread = threading.Thread(
            target=server.start,
            daemon=True
        )
        server_thread.start()
        
        # Only start RAFT timers if requested
        if start_timers:  # ← Add this condition
            raft_node.start_raft_node()
        
        print(f"[Node {node_id}] ✓ Started successfully")
    
    def start_all_nodes(self):
        """Start all nodes in the cluster"""
        print("\n" + "="*60)
        print("RAFT Cluster Startup - Phase 1: Initialize RPC Servers")
        print("="*60)
        
        # PHASE 1: Start all RPC servers WITHOUT starting election timers
        for node_id in sorted(self.config.keys()):
            self.start_node(node_id, start_timers=False)  # ← Pass False
        
        print("\n[Cluster] All RPC servers started. Waiting for stabilization...")
        time.sleep(1)  # Let RPC servers fully start
        
        print("\n" + "="*60)
        print("RAFT Cluster Startup - Phase 2: Begin Leader Election")
        print("="*60)
        
        # PHASE 2: Now start election timers on all nodes together
        for node_id, node in self.nodes.items():
            print(f"[Cluster] Starting election timer for Node {node_id}")
            node.start_raft_node()  # ← Start timers NOW
        
        print("\n[Cluster] All nodes ready for leader election!")
        
    def wait_for_leader(self, timeout=10):
        """Wait for a leader to be elected"""
        print(f"\n[Cluster] Waiting up to {timeout} seconds for leader election...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            for node_id, node in self.nodes.items():
                if node.raft_terms.state.name == "leader":
                    print(f"\n✨ [CLUSTER] Node {node_id} elected as LEADER in term {node.raft_terms.current_term}")
                    return node_id
            
            time.sleep(0.5)
        
        print("[Cluster] ⚠️  No leader elected within timeout")
        return None
    
    def print_cluster_status(self):
        """Print the status of all nodes"""
        print("\n" + "="*60)
        print("CLUSTER STATUS")
        print("="*60)
        
        for node_id in sorted(self.nodes.keys()):
            node = self.nodes[node_id]
            print(f"\nNode {node_id}:")
            print(f"  State:        {node.raft_terms.state.name.upper()}")
            print(f"  Term:         {node.raft_terms.current_term}")
            print(f"  Voted For:    {node.raft_terms.voted_for}")
            print(f"  Last Log:     index={node.raft_terms.last_log_index}, term={node.raft_terms.last_log_term}")
            print(f"  Commit Index: {node.raft_terms.commit_index}")


def main():
    """Main function to run the cluster"""
    
    cluster = RaftCluster(CLUSTER_CONFIG)
    
    try:
        # Start all nodes
        cluster.start_all_nodes()
        
        # Wait a bit for nodes to discover each other
        time.sleep(2)
        
        # Print initial status
        cluster.print_cluster_status()
        
        # Wait for leader election
        leader_id = cluster.wait_for_leader(timeout=15)
        
        # Print final status
        time.sleep(1)
        cluster.print_cluster_status()
        
        if leader_id:
            print("\n" + "="*60)
            print("✨ LEADER ELECTION SUCCESSFUL!")
            print("="*60)
            print(f"\nCluster is running with Node {leader_id} as leader.")
            print("\nThe cluster will continue running. Press Ctrl+C to stop.\n")
        else:
            print("\n" + "="*60)
            print("⚠️  LEADER ELECTION FAILED")
            print("="*60)
        
        # Keep running
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\n[Cluster] Shutting down...")
        for node_id, node in cluster.nodes.items():
            node.kill()
        print("[Cluster] ✓ All nodes stopped")


if __name__ == "__main__":
    main()