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
        
        # Delay tracking
        self._data_receive_times = []  # Queue of (timestamp, data) for delay calculation
        self._recent_delays = []  # Track recent delays for averaging
        self._max_delay_history = 100  # Keep last 100 delay measurements
        
        # Sampling rate tracking  
        self._sample_timestamps = []  # Track when samples arrive
        self._samples_per_message = 0
        self._calculated_sample_rate = 30000.0  # Default fallback
        self._mean_sample_rate = 30000.0  # 10-second mean rate
        self._rate_history = []  # Keep rate measurements for mean calculation
        
        # Data flow tracking
        self._last_data_time = 0
        self._data_flow_active = False
        
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
            # Subscribe to status updates for reinit events
            self._event_bus.subscribe(EventType.STATUS_UPDATE, self._on_status_update)
            
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
    
    def _update_sampling_rate(self) -> None:
        """Calculate actual sampling rate from incoming data."""
        if len(self._sample_timestamps) < 2:
            return
            
        # Calculate time span and total samples
        time_span = self._sample_timestamps[-1] - self._sample_timestamps[0]
        if time_span <= 0:
            return
            
        # Number of sample packets received
        num_packets = len(self._sample_timestamps)
        total_samples = num_packets * self._samples_per_message
        
        # Calculate actual sampling rate
        current_rate = total_samples / time_span
        self._calculated_sample_rate = current_rate
        
        # Update rate history for mean calculation (keep last 10 seconds of measurements)
        current_time = time.time()
        self._rate_history.append((current_time, current_rate))
        
        # Remove old measurements (older than 10 seconds)
        self._rate_history = [(t, r) for t, r in self._rate_history if current_time - t <= 10.0]
        
        # Calculate mean rate from last 10 seconds
        if self._rate_history:
            self._mean_sample_rate = sum(r for _, r in self._rate_history) / len(self._rate_history)
    
    def get_delay_stats(self) -> dict:
        """Get current delay statistics."""
        if not self._recent_delays:
            return {
                "avg_delay_ms": 0.0,
                "min_delay_ms": 0.0,
                "max_delay_ms": 0.0,
                "queue_size": len(self._data_queue)
            }
        
        return {
            "avg_delay_ms": sum(self._recent_delays) / len(self._recent_delays),
            "min_delay_ms": min(self._recent_delays),
            "max_delay_ms": max(self._recent_delays),
            "queue_size": len(self._data_queue),
            "sample_rate": self._calculated_sample_rate
        }
    
    def stop(self) -> None:
        """Stop the OSC service."""
        self._running = False
        
        # Unsubscribe from events
        try:
            self._event_bus.unsubscribe(EventType.DATA_PROCESSED, self._on_data_received)
            self._event_bus.unsubscribe(EventType.STATUS_UPDATE, self._on_status_update)
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
            receive_time = time.time()
            
            # Update data flow tracking
            self._last_data_time = receive_time
            self._data_flow_active = True
            
            # Track for delay calculation
            self._data_receive_times.append(receive_time)
            # Keep only recent timestamps
            if len(self._data_receive_times) > self._max_delay_history:
                self._data_receive_times.pop(0)
            
            # Track for sampling rate calculation
            num_samples = event.data.get("num_samples", 0)
            if num_samples > 0:
                self._samples_per_message = num_samples
                self._sample_timestamps.append(receive_time)
                # Keep only recent timestamps (last 50 for ~1.5 second window)
                if len(self._sample_timestamps) > 50:
                    self._sample_timestamps.pop(0)
                self._update_sampling_rate()
            
            with self._queue_lock:
                self._data_queue.append((receive_time, datalist, event.data.get("chunk_delay_ms", 0.0)))
    
    def _run(self) -> None:
        """Main processing loop."""
        while self._running:
            current_time = time.time()
            data_to_process = None
            
            # Check if data flow has stopped (no data for 2 seconds)
            if self._data_flow_active and (current_time - self._last_data_time) > 2.0:
                self._data_flow_active = False
                # Reset sampling rate when no data
                self._calculated_sample_rate = 0.0
            
            with self._queue_lock:
                if self._data_queue:
                    data_to_process = self._data_queue.pop(0)
            
            if data_to_process:
                receive_time, datalist, chunk_delay = data_to_process
                send_time = time.time()
                
                # Calculate and track delay
                delay_ms = (send_time - receive_time) * 1000  # Convert to milliseconds
                self._recent_delays.append(delay_ms)
                if len(self._recent_delays) > self._max_delay_history:
                    self._recent_delays.pop(0)
                
                self._send_data(datalist, delay_ms, chunk_delay)
            else:
                # Minimal sleep for high-performance real-time processing
                time.sleep(0.0001)  # 0.1ms instead of 1ms for lower latency
    
    def _send_data(self, datalist: List[np.ndarray], delay_ms: float = 0.0, chunk_delay: float = 0.0) -> None:
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
            
            # Calculate statistics
            avg_delay = sum(self._recent_delays) / len(self._recent_delays) if self._recent_delays else 0.0
            queue_size = len(self._data_queue)
            
            # Determine if we should show zero values with indicators
            display_delay = avg_delay if self._data_flow_active else 0.0
            display_rate = self._calculated_sample_rate if self._data_flow_active else 0.0
            display_mean_rate = self._mean_sample_rate if self._data_flow_active else 0.0
            
            # Publish send confirmation with delay and sampling rate info
            self._event_bus.publish_event(
                EventType.DATA_SENT,
                data={
                    "num_channels": len(datalist),
                    "num_samples": len(datalist[0]) if datalist else 0,
                    "messages_sent": self._messages_sent,
                    "queue_size": queue_size,
                    "delay_ms": delay_ms,
                    "avg_delay_ms": display_delay,
                    "calculated_sample_rate": display_rate,
                    "mean_sample_rate": display_mean_rate,
                    "data_flow_active": self._data_flow_active,
                    "chunk_delay_ms": chunk_delay
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
    
    def _on_status_update(self, event) -> None:
        """Handle status update events for reinit."""
        if not event.data:
            return
            
        event_type = event.data.get("type")
        
        if event_type in ["auto_reinit_completed", "manual_reinit_completed"]:
            # Reset all sampling rate and delay tracking when reinit occurs
            self._calculated_sample_rate = 0.0
            self._mean_sample_rate = 0.0
            self._recent_delays = []
            self._sample_timestamps = []
            self._rate_history = []
            self._data_flow_active = False
            self._last_data_time = 0
            
            # Immediately publish reset status to update UI
            self._event_bus.publish_event(
                EventType.DATA_SENT,
                data={
                    "num_channels": 0,
                    "num_samples": 0,
                    "messages_sent": self._messages_sent,
                    "queue_size": 0,
                    "delay_ms": 0.0,
                    "avg_delay_ms": 0.0,
                    "calculated_sample_rate": 0.0,
                    "mean_sample_rate": 0.0,
                    "data_flow_active": False,
                    "chunk_delay_ms": 0.0
                },
                source="OSCService"
            )
            print("OSC metrics reset due to data reinit")
    
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