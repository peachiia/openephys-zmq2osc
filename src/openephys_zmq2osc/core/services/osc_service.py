import threading
import time
from typing import Optional, List, Union
import numpy as np
from pythonosc import udp_client

from ..events.event_bus import get_event_bus, EventType, Event
from ..utils.signal_processing import SignalProcessor, validate_downsampling_config


class OSCService:
    def __init__(self, host: str = "127.0.0.1", port: int = 10000, config=None):
        self.host = host
        self.port = port
        self.client: Optional[udp_client.SimpleUDPClient] = None

        self._running = False
        self._event_bus = get_event_bus()
        self._data_queue = []
        self._queue_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        # Performance configuration
        self._config = config
        self._batch_size = 1  # Default to no batching
        self._queue_max_size = 100
        self._queue_overflow_strategy = "drop_oldest"
        self._batching_enabled = True

        if config and hasattr(config, "performance"):
            perf = config.performance
            self._batch_size = perf.osc_batch_size if perf.enable_batching else 1
            self._queue_max_size = perf.osc_queue_max_size
            self._queue_overflow_strategy = perf.osc_queue_overflow_strategy
            self._batching_enabled = perf.enable_batching

        # Queue monitoring
        self._queue_overflows = 0
        self._messages_dropped = 0

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
        
        # Signal processing and downsampling
        self.signal_processor = SignalProcessor(config)
        self.downsampling_factor = 1
        self.downsampling_method = "average"
        self.chunk_format = "timestamped"
        self.chunk_include_metadata = True
        
        if config and hasattr(config, "osc"):
            osc_config = config.osc
            self.downsampling_factor = getattr(osc_config, 'downsampling_factor', 1)
            self.downsampling_method = getattr(osc_config, 'downsampling_method', 'average')
            self.chunk_format = getattr(osc_config, 'chunk_format', 'timestamped')
            self.chunk_include_metadata = getattr(osc_config, 'chunk_include_metadata', True)
        
        # Validate downsampling config
        is_valid, error_msg = validate_downsampling_config(self.downsampling_factor, self.downsampling_method)
        if not is_valid:
            print(f"Warning: Invalid downsampling config: {error_msg}. Using defaults.")
            self.downsampling_factor = 1
            self.downsampling_method = "average"

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
                source="OSCService",
            )

            # Publish initial OSC status with batch size info
            self._event_bus.publish_event(
                EventType.OSC_CONNECTION_STATUS,
                data={
                    "running": True,
                    "connected": True,
                    "host": self.host,
                    "port": self.port,
                    "batch_size": self._batch_size,
                    "messages_sent": 0,
                    "queue_size": 0,
                },
                source="OSCService",
            )

            print(f"OSC service started - sending to {self.host}:{self.port}")

        except Exception as e:
            self._connection_active = False
            self._event_bus.publish_event(
                EventType.OSC_CONNECTION_ERROR,
                data={"error": str(e), "host": self.host, "port": self.port},
                source="OSCService",
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
        self._rate_history = [
            (t, r) for t, r in self._rate_history if current_time - t <= 10.0
        ]

        # Calculate mean rate from last 10 seconds
        if self._rate_history:
            self._mean_sample_rate = sum(r for _, r in self._rate_history) / len(
                self._rate_history
            )

    def get_delay_stats(self) -> dict:
        """Get current delay statistics."""
        if not self._recent_delays:
            return {
                "avg_delay_ms": 0.0,
                "min_delay_ms": 0.0,
                "max_delay_ms": 0.0,
                "queue_size": len(self._data_queue),
            }

        return {
            "avg_delay_ms": sum(self._recent_delays) / len(self._recent_delays),
            "min_delay_ms": min(self._recent_delays),
            "max_delay_ms": max(self._recent_delays),
            "queue_size": len(self._data_queue),
            "sample_rate": self._calculated_sample_rate,
        }

    def stop(self) -> None:
        """Stop the OSC service."""
        self._running = False

        # Unsubscribe from events
        try:
            self._event_bus.unsubscribe(
                EventType.DATA_PROCESSED, self._on_data_received
            )
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
                if hasattr(self.client, "close"):
                    self.client.close()
                self.client = None
        except Exception as e:
            print(f"Error cleaning up OSC client: {e}")

        # Publish stopped event (if event bus is still working)
        try:
            self._event_bus.publish_event(
                EventType.SERVICE_STOPPED, source="OSCService"
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

            # Initialize signal processor with channel count if needed
            if len(datalist) > 0 and self.signal_processor.num_channels == 0:
                self.signal_processor.initialize(len(datalist))

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

            # Queue management with overflow handling
            with self._queue_lock:
                # Check if queue is full and handle overflow
                if len(self._data_queue) >= self._queue_max_size:
                    self._handle_queue_overflow()

                self._data_queue.append(
                    (receive_time, datalist, event.data.get("batch_delay_ms", 0.0))
                )

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
                receive_time, datalist, batch_delay = data_to_process
                send_time = time.time()

                # Calculate and track delay
                delay_ms = (send_time - receive_time) * 1000  # Convert to milliseconds
                self._recent_delays.append(delay_ms)
                if len(self._recent_delays) > self._max_delay_history:
                    self._recent_delays.pop(0)

                self._send_data(datalist, delay_ms, batch_delay)
            else:
                # Minimal sleep to prevent CPU spinning while still being responsive
                time.sleep(0.001)  # 1ms - balance between CPU usage and responsiveness

    def _handle_queue_overflow(self) -> None:
        """Handle queue overflow based on configured strategy."""
        self._queue_overflows += 1

        if self._queue_overflow_strategy == "drop_oldest":
            if self._data_queue:
                self._data_queue.pop(0)
                self._messages_dropped += 1
        elif self._queue_overflow_strategy == "drop_newest":
            # Don't add the new item (caller will handle)
            self._messages_dropped += 1
        # "block" strategy does nothing - queue will grow (original behavior)

    def _send_data(
        self,
        datalist: List[np.ndarray],
        delay_ms: float = 0.0,
        batch_delay: float = 0.0,
    ) -> None:
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
            avg_delay = (
                sum(self._recent_delays) / len(self._recent_delays)
                if self._recent_delays
                else 0.0
            )
            queue_size = len(self._data_queue)

            # Determine if we should show zero values with indicators
            display_delay = avg_delay if self._data_flow_active else 0.0
            display_rate = (
                self._calculated_sample_rate if self._data_flow_active else 0.0
            )
            display_mean_rate = (
                self._mean_sample_rate if self._data_flow_active else 0.0
            )

            # Calculate actual OSC messages sent (accounting for batching)
            actual_messages_sent = self._calculate_messages_sent(datalist)

            # Publish send confirmation with delay and sampling rate info
            self._event_bus.publish_event(
                EventType.DATA_SENT,
                data={
                    "num_channels": len(datalist),
                    "num_samples": len(datalist[0]) if datalist else 0,
                    "messages_sent": self._messages_sent,
                    "actual_osc_messages": actual_messages_sent,
                    "batch_size": self._batch_size,
                    "queue_size": queue_size,
                    "queue_overflows": self._queue_overflows,
                    "messages_dropped": self._messages_dropped,
                    "delay_ms": delay_ms,
                    "avg_delay_ms": display_delay,
                    "calculated_sample_rate": display_rate,
                    "mean_sample_rate": display_mean_rate,
                    "data_flow_active": self._data_flow_active,
                    "batch_delay_ms": batch_delay,
                },
                source="OSCService",
            )

        except Exception as e:
            self._connection_active = False
            self._event_bus.publish_event(
                EventType.OSC_CONNECTION_ERROR,
                data={
                    "error": str(e),
                    "host": self.host,
                    "port": self.port,
                    "action": "sending_data",
                },
                source="OSCService",
            )

    def _calculate_messages_sent(self, datalist: List[np.ndarray]) -> int:
        """Calculate actual number of OSC messages sent accounting for batching."""
        if not datalist:
            return 0

        total_samples = len(datalist[0]) if datalist else 0

        if self._batching_enabled and self._batch_size > 1:
            # Calculate number of batch messages
            return (total_samples + self._batch_size - 1) // self._batch_size
        else:
            # No batching - one message per sample
            return total_samples

    def _send_individual_channels(self, datalist: List[np.ndarray]) -> None:
        """Send each channel as individual OSC messages."""
        for channel_idx, channel_data in enumerate(datalist):
            address = self.channel_address_format.format(channel_idx)

            if isinstance(channel_data, np.ndarray):
                # Convert to list once per channel instead of checking per sample
                sample_list = channel_data.tolist()
                for sample in sample_list:
                    self.client.send_message(address, sample)
            else:
                self.client.send_message(address, channel_data)

    def _send_combined_data(self, datalist: List[np.ndarray]) -> None:
        """Send all channels as combined data with new mode support."""
        # Convert to numpy array and transpose for sample-wise processing
        if isinstance(datalist, list):
            data_array = np.array(datalist)
        else:
            data_array = datalist

        # Transpose to have samples as rows, channels as columns
        transposed_data = data_array.T

        if self._batching_enabled and self._batch_size > 1:
            # CHUNK BATCH MODE - Enhanced batching with new formats
            self._send_chunk_batch_mode(transposed_data)
        else:
            # INDIVIDUAL SAMPLE MODE - With downsampling support
            self._send_individual_sample_mode(transposed_data)

    def _send_batched_samples(self, transposed_data: np.ndarray) -> None:
        """Send samples in batches for improved performance."""
        total_samples = len(transposed_data)

        # Convert entire array to list once for efficiency
        sample_list = transposed_data.tolist()

        # Send samples in batches
        for i in range(0, total_samples, self._batch_size):
            end_idx = min(i + self._batch_size, total_samples)

            if end_idx - i == 1:
                # Single sample - use original format (avoid extra conversion)
                self.client.send_message(self.base_address, sample_list[i])
            else:
                # Multiple samples - send as batch with batch address
                batch_data = sample_list[i:end_idx]
                batch_address = f"{self.base_address}/batch/{len(batch_data)}"
                self.client.send_message(batch_address, batch_data)
    
    def _send_individual_sample_mode(self, transposed_data: np.ndarray) -> None:
        """Send samples individually with downsampling support."""
        # Process samples through signal processor for downsampling
        processed_samples = self.signal_processor.process_samples(transposed_data)
        
        # Send each processed sample to /data/sample
        sample_address = f"{self.base_address}/sample"
        for sample_data in processed_samples:
            if isinstance(sample_data, np.ndarray):
                sample_list = sample_data.tolist()
            else:
                sample_list = sample_data
            self.client.send_message(sample_address, sample_list)
    
    def _send_chunk_batch_mode(self, transposed_data: np.ndarray) -> None:
        """Send samples in enhanced chunk batch mode."""
        total_samples = len(transposed_data)
        num_channels = transposed_data.shape[1] if len(transposed_data.shape) > 1 else 1
        
        # Convert to list format for OSC transmission
        sample_list = transposed_data.tolist()
        
        # Send samples in batches based on configured batch size
        for i in range(0, total_samples, self._batch_size):
            end_idx = min(i + self._batch_size, total_samples)
            batch_data = sample_list[i:end_idx]
            batch_size = end_idx - i
            
            if self.chunk_format == "timestamped":
                self._send_timestamped_chunk(batch_data, batch_size, num_channels)
            elif self.chunk_format == "simple_array":
                self._send_simple_array_chunk(batch_data, batch_size, num_channels)
            else:
                # Fallback to original batching
                if batch_size == 1:
                    self.client.send_message(self.base_address, batch_data[0])
                else:
                    batch_address = f"{self.base_address}/batch/{batch_size}"
                    self.client.send_message(batch_address, batch_data)
    
    def _send_timestamped_chunk(self, batch_data: List, batch_size: int, num_channels: int) -> None:
        """Send chunk with timestamp and metadata (recommended format)."""
        chunk_address = f"{self.base_address}/chunk"
        current_time = time.time()
        
        if self.chunk_include_metadata:
            # Format: [timestamp, num_samples, num_channels, ...flattened_data...]
            flattened_data = []
            for sample in batch_data:
                flattened_data.extend(sample)
            
            chunk_message = [current_time, batch_size, num_channels] + flattened_data
        else:
            # Format: [timestamp, ...flattened_data...]
            flattened_data = []
            for sample in batch_data:
                flattened_data.extend(sample)
            
            chunk_message = [current_time] + flattened_data
        
        self.client.send_message(chunk_address, chunk_message)
    
    def _send_simple_array_chunk(self, batch_data: List, batch_size: int, num_channels: int) -> None:
        """Send chunk as simple flattened array with size in address."""
        chunk_address = f"{self.base_address}/chunk/{batch_size}x{num_channels}"
        
        # Flatten data: [sample1_ch1, sample1_ch2, ..., sample2_ch1, sample2_ch2, ...]
        flattened_data = []
        for sample in batch_data:
            flattened_data.extend(sample)
        
        self.client.send_message(chunk_address, flattened_data)

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
            # Reset drop counter only on reinit
            self._messages_dropped = 0
            # Reset signal processor
            self.signal_processor.reset()

            # Immediately publish reset status to update UI
            self._event_bus.publish_event(
                EventType.DATA_SENT,
                data={
                    "num_channels": 0,
                    "num_samples": 0,
                    "messages_sent": self._messages_sent,
                    "queue_size": 0,
                    "queue_overflows": self._queue_overflows,
                    "messages_dropped": self._messages_dropped,
                    "delay_ms": 0.0,
                    "avg_delay_ms": 0.0,
                    "calculated_sample_rate": 0.0,
                    "mean_sample_rate": 0.0,
                    "data_flow_active": False,
                    "batch_delay_ms": 0.0,
                },
                source="OSCService",
            )

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
        if "downsampling_factor" in kwargs:
            factor = kwargs["downsampling_factor"]
            is_valid, error_msg = validate_downsampling_config(factor, self.downsampling_method)
            if is_valid:
                self.downsampling_factor = factor
                # Recreate signal processor with new config
                if hasattr(self, 'signal_processor'):
                    self.signal_processor.downsampling_factor = factor
                    if self.signal_processor.num_channels > 0:
                        self.signal_processor.initialize(self.signal_processor.num_channels)
            else:
                print(f"Invalid downsampling factor: {error_msg}")
        if "downsampling_method" in kwargs:
            method = kwargs["downsampling_method"]
            is_valid, error_msg = validate_downsampling_config(self.downsampling_factor, method)
            if is_valid:
                self.downsampling_method = method
                if hasattr(self, 'signal_processor'):
                    self.signal_processor.downsampling_method = method
                    if self.signal_processor.num_channels > 0:
                        self.signal_processor.initialize(self.signal_processor.num_channels)
            else:
                print(f"Invalid downsampling method: {error_msg}")
        if "chunk_format" in kwargs:
            self.chunk_format = kwargs["chunk_format"]
        if "chunk_include_metadata" in kwargs:
            self.chunk_include_metadata = kwargs["chunk_include_metadata"]

        # If service is running, restart with new configuration
        if self._running:
            print("Restarting OSC service with new configuration...")
            self.stop()
            time.sleep(0.1)
            self.start()

    def get_status(self) -> dict:
        """Get current service status."""
        status = {
            "running": self._running,
            "connected": self._connection_active,
            "host": self.host,
            "port": self.port,
            "base_address": self.base_address,
            "send_individual_channels": self.send_individual_channels,
            "channel_address_format": self.channel_address_format,
            "messages_sent": self._messages_sent,
            "last_send_time": self._last_send_time,
            "queue_size": len(self._data_queue),
            "downsampling_factor": self.downsampling_factor,
            "downsampling_method": self.downsampling_method,
            "chunk_format": self.chunk_format,
            "batching_enabled": self._batching_enabled,
        }
        
        # Add signal processor status if available
        if hasattr(self, 'signal_processor') and self.signal_processor:
            status.update(self.signal_processor.get_status())
        
        return status

    def get_statistics(self) -> dict:
        """Get service statistics."""
        current_time = time.time()
        return {
            "messages_sent": self._messages_sent,
            "last_send_time": self._last_send_time,
            "time_since_last_send": current_time - self._last_send_time
            if self._last_send_time
            else 0,
            "queue_size": len(self._data_queue),
            "connection_active": self._connection_active,
        }
