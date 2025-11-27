import enum

class RaftState(enum.Enum):
    leader = "Leader"
    follower = "Follower"
    candidate = "Candidate"
    