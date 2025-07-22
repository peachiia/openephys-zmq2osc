import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    # Connection events
    ZMQ_CONNECTION_STATUS = "zmq_connection_status"
    ZMQ_CONNECTION_ERROR = "zmq_connection_error"
    OSC_CONNECTION_STATUS = "osc_connection_status"
    OSC_CONNECTION_ERROR = "osc_connection_error"

    # Data events
    DATA_RECEIVED = "data_received"
    DATA_PROCESSED = "data_processed"
    DATA_SENT = "data_sent"

    # System events
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    SHUTDOWN_REQUESTED = "shutdown_requested"

    # UI events
    UI_UPDATE_REQUIRED = "ui_update_required"
    STATUS_UPDATE = "status_update"


@dataclass
class Event:
    event_type: EventType
    data: Any = None
    timestamp: datetime = None
    source: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class EventBus:
    def __init__(self):
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(
        self, event_type: EventType, callback: Callable[[Event], None]
    ) -> None:
        """Subscribe to an event type with a callback function."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def unsubscribe(
        self, event_type: EventType, callback: Callable[[Event], None]
    ) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass  # Callback wasn't subscribed

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        subscribers = []
        with self._lock:
            if event.event_type in self._subscribers:
                subscribers = self._subscribers[event.event_type].copy()

        # Call subscribers outside of lock to prevent deadlocks
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                # Log error but don't stop other callbacks
                print(f"Error in event callback for {event.event_type}: {e}")

    def publish_event(
        self, event_type: EventType, data: Any = None, source: str = None
    ) -> None:
        """Convenience method to create and publish an event."""
        event = Event(event_type=event_type, data=data, source=source)
        self.publish(event)

    def clear_subscribers(self, event_type: EventType = None) -> None:
        """Clear subscribers for a specific event type or all event types."""
        with self._lock:
            if event_type is None:
                self._subscribers.clear()
            elif event_type in self._subscribers:
                self._subscribers[event_type].clear()


# Global event bus instance
_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    return _event_bus
