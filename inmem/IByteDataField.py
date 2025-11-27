from abc import ABC, abstractmethod

class IByteDataField(ABC):
    
    @abstractmethod
    def is_alive(self, timestamp: int) -> bool:
        pass
