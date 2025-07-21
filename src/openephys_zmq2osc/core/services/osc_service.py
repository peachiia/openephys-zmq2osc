import threading
import time
from typing import Optional, List, Union
import numpy as np
from pythonosc import udp_client

from ..events.event_bus import get_event_bus, EventType, Event


class OSCService:
    def __init__(self, host: str = "127.0.0.1", port: int = 10000):
        self.host = host
        self.port = port
        self.client: Optional[udp_client.SimpleUDPClient] = None
        
        self._running = False
        self._event_bus = get_event_bus()
        self._data_queue = []
        self._queue_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        
        # Statistics
        self._messages_sent = 0
        self._last_send_time = 0
        self._connection_active = False
        
        # Configuration
        self.base_address = "/data"
        self.send_individual_channels = False
        self.channel_address_format = "/ch{:03d}"
        
    def start(self) -> None:
        """Start the OSC service."""
        if self._running:
            return
            
        try:
            self.client = udp_client.SimpleUDPClient(self.host, self.port)
            self._connection_active = True
            self._running = True
            
            # Subscribe to data events from ZMQ service
            self._event_bus.subscribe(EventType.DATA_PROCESSED, self._on_data_received)
            
            # Start processing thread
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            
            self._event_bus.publish_event(
                EventType.SERVICE_STARTED,
                data={"host": self.host, "port": self.port},
                source="OSCService"
            )
            
            print(f"OSC service started - sending to {self.host}:{self.port}")
            
        except Exception as e:
            self._connection_active = False
            self._event_bus.publish_event(
                EventType.OSC_CONNECTION_ERROR,
                data={"error": str(e), "host": self.host, "port": self.port},
                source="OSCService"
            )
    
    def stop(self) -> None:
        """Stop the OSC service."""
        self._running = False
        
        # Unsubscribe from events
        try:
            self._event_bus.unsubscribe(EventType.DATA_PROCESSED, self._on_data_received)
        except Exception as e:
            print(f"Error unsubscribing from events: {e}")
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=5.0)
                if self._thread.is_alive():
                    print("Warning: OSC thread did not terminate within timeout")
            except Exception as e:
                print(f"Error joining OSC thread: {e}")
                
        # Cleanup client
        try:
            self._connection_active = False
            if self.client:
                # If the client has explicit cleanup, call it
                if hasattr(self.client, 'close'):
                    self.client.close()
                self.client = None
        except Exception as e:
            print(f"Error cleaning up OSC client: {e}")
        
        # Publish stopped event (if event bus is still working)
        try:
            self._event_bus.publish_event(
                EventType.SERVICE_STOPPED,
                source="OSCService"
            )
        except Exception as e:
            print(f"Error publishing service stopped event: {e}")
    
    def _on_data_received(self, event: Event) -> None:
        """Handle data received from ZMQ service."""
        if not self._running or not event.data:
            return
            
        datalist = event.data.get("datalist")
        if datalist:
            with self._queue_lock:
                self._data_queue.append(datalist)
    
    def _run(self) -> None:
        """Main processing loop."""
        while self._running:
            data_to_process = None
            
            with self._queue_lock:
                if self._data_queue:
                    data_to_process = self._data_queue.pop(0)
            
            if data_to_process:
                self._send_data(data_to_process)
            else:
                # Minimal sleep for high-performance real-time processing
                time.sleep(0.0001)  # 0.1ms instead of 1ms for lower latency
    
    def _send_data(self, datalist: List[np.ndarray]) -> None:
        """Send data via OSC."""
        if not self.client or not self._connection_active:
            return
            
        try:
            if self.send_individual_channels:
                self._send_individual_channels(datalist)
            else:
                self._send_combined_data(datalist)
                
            self._messages_sent += 1
            self._last_send_time = time.time()
            
            # Publish send confirmation
            self._event_bus.publish_event(
                EventType.DATA_SENT,
                data={
                    "num_channels": len(datalist),
                    "num_samples": len(datalist[0]) if datalist else 0,
                    "messages_sent": self._messages_sent
                },
                source="OSCService"
            )
            
        except Exception as e:
            self._connection_active = False
            self._event_bus.publish_event(
                EventType.OSC_CONNECTION_ERROR,
                data={
                    "error": str(e),
                    "host": self.host,
                    "port": self.port,
                    "action": "sending_data"
                },
                source="OSCService"
            )
    
    def _send_individual_channels(self, datalist: List[np.ndarray]) -> None:
        """Send each channel as individual OSC messages."""
        for channel_idx, channel_data in enumerate(datalist):
            if isinstance(channel_data, np.ndarray):
                channel_data = channel_data.tolist()
            
            address = self.channel_address_format.format(channel_idx)
            
            if isinstance(channel_data, list):
                for sample in channel_data:
                    self.client.send_message(address, sample)
            else:
                self.client.send_message(address, channel_data)
    
    def _send_combined_data(self, datalist: List[np.ndarray]) -> None:
        """Send all channels as combined data."""
        # Convert to numpy array and transpose for sample-wise sending
        if isinstance(datalist, list):
            data_array = np.array(datalist)
        else:
            data_array = datalist
            
        # Transpose to have samples as rows, channels as columns
        transposed_data = data_array.T
        
        # Send each sample (all channels) as one message
        for sample_idx, sample_data in enumerate(transposed_data):
            self.client.send_message(self.base_address, sample_data.tolist())
    
    def send_message(self, address: str, value: Union[float, int, str, List]) -> bool:
        """Send a custom OSC message."""
        if not self.client or not self._connection_active:
            return False
            
        try:
            self.client.send_message(address, value)
            return True
        except Exception as e:
            print(f"Error sending custom OSC message: {e}")
            return False
    
    def configure(self, **kwargs) -> None:
        """Configure OSC service parameters."""
        if "host" in kwargs:
            self.host = kwargs["host"]
        if "port" in kwargs:
            self.port = kwargs["port"]
        if "base_address" in kwargs:
            self.base_address = kwargs["base_address"]
        if "send_individual_channels" in kwargs:
            self.send_individual_channels = kwargs["send_individual_channels"]
        if "channel_address_format" in kwargs:
            self.channel_address_format = kwargs["channel_address_format"]
        
        # If service is running, restart with new configuration
        if self._running:
            print("Restarting OSC service with new configuration...")
            self.stop()
            time.sleep(0.1)
            self.start()
    
    def get_status(self) -> dict:
        """Get current service status."""
        return {
            "running": self._running,
            "connected": self._connection_active,
            "host": self.host,
            "port": self.port,
            "base_address": self.base_address,
            "send_individual_channels": self.send_individual_channels,
            "channel_address_format": self.channel_address_format,
            "messages_sent": self._messages_sent,
            "last_send_time": self._last_send_time,
            "queue_size": len(self._data_queue)
        }
    
    def get_statistics(self) -> dict:
        """Get service statistics."""
        current_time = time.time()
        return {
            "messages_sent": self._messages_sent,
            "last_send_time": self._last_send_time,
            "time_since_last_send": current_time - self._last_send_time if self._last_send_time else 0,
            "queue_size": len(self._data_queue),
            "connection_active": self._connection_active
        }