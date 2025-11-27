from dataclasses import dataclass

@dataclass
class VoteArguments:
    """
    RequestVote RPC Arguments
    Raft Paper §5.1: Arguments for RequestVote RPC
    
    Sent by candidates during leader election (§5.2)
    """
    current_term: int      # Candidate's current term
    candidate_id: int      # Candidate requesting vote
    last_log_index: int    # Index of candidate's last log entry (§5.4)
    last_log_term: int     # Term of candidate's last log entry (§5.4)