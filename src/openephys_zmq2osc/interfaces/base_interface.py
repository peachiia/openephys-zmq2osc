from abc import ABC, abstractmethod
from typing import Dict, Any
from ..config.settings import Config


class BaseInterface(ABC):
    """Abstract base class for user interfaces."""

    def __init__(self, config: Config):
        self.config = config
        self._running = False

    @abstractmethod
    def start(self) -> None:
        """Start the interface."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the interface."""
        pass

    @abstractmethod
    def update_zmq_status(self, status_data: Dict[str, Any]) -> None:
        """Update ZMQ connection status display."""
        pass

    @abstractmethod
    def update_osc_status(self, status_data: Dict[str, Any]) -> None:
        """Update OSC connection status display."""
        pass

    @abstractmethod
    def update_data_stats(self, stats_data: Dict[str, Any]) -> None:
        """Update data processing statistics."""
        pass

    @abstractmethod
    def show_error(self, error_message: str, source: str = None) -> None:
        """Display an error message."""
        pass

    @abstractmethod
    def show_message(self, message: str, level: str = "info") -> None:
        """Display a general message."""
        pass

    @property
    def is_running(self) -> bool:
        """Check if the interface is running."""
        return self._running
