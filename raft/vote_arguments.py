from dataclasses import dataclass

@dataclass
class VoteArguments:
    """
    RequestVote RPC Arguments
    Raft Paper §5.1: Arguments for RequestVote RPC
    
    Sent by candidates during leader election (§5.2)
    """
    candidate_id: int      # Candidate requesting vote
    current_term: int      # Candidate's current term
    last_log_index: int    # Index of candidate's last log entry (§5.4)
    last_log_term: int     # Term of candidate's last log entry (§5.4)