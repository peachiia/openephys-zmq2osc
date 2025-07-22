import zmq
import json
import time
import numpy as np
import threading
from enum import Enum
from typing import Optional, Dict, Any

from ..models.openephys_objects import OpenEphysEventObject, OpenEphysSpikeObject
from ..events.event_bus import get_event_bus, EventType, Event
from .data_manager import DataManager


class ConnectionStatus(Enum):
    NOT_CONNECTED = "not_connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    CONNECTING = "connecting"
    CONNECTED = "connected" 
    ONLINE = "online"
    NOT_RESPONDING = "not_responding"


class ZMQService:
    def __init__(self, ip: str = "localhost", data_port: int = 5556, config=None):
        self.context: Optional[zmq.Context] = None
        self.heartbeat_socket: Optional[zmq.Socket] = None
        self.data_socket: Optional[zmq.Socket] = None
        self.poller: Optional[zmq.Poller] = None
        
        self.ip = ip
        self.data_port = data_port
        self.heartbeat_port = data_port + 1
        self.protocol = "tcp://"
        
        self.message_num = 0
        self.socket_waits_reply = False
        self.uuid = "1618"  # Consider making this configurable
        self.app_name = f'OpenEphys-ZMQ2OSC-{self.uuid[:4]}'
        
        self.last_heartbeat_timestamp = 0
        self.last_reply_timestamp = time.time()
        
        # Timeout configurations
        self.heartbeat_timeout_duration = 2.0  # seconds
        self.not_responding_timeout_duration = 10.0  # seconds
        
        # Connection status
        self.connection_status = ConnectionStatus.NOT_CONNECTED
        
        # Data management with dynamic channel discovery
        self.data_manager = DataManager()
        # Start with minimal buffer, will expand dynamically
        self.data_manager.init_empty_buffer(num_channels=1, num_samples=30000)
        
        # Configure timeout settings if config provided
        if config and hasattr(config, 'zmq'):
            self.data_manager.configure_timeout(
                timeout_seconds=config.zmq.data_timeout_seconds,
                auto_reinit=config.zmq.auto_reinit_on_timeout
            )
        
        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_bus = get_event_bus()
        
        # Chunk delay tracking
        self._last_chunk_samples = 0
        self._estimated_sample_rate = 30000.0  # Default fallback
        self._chunk_delay_ms = 0.0
        
        # Subscribe to manual reinit events and data sent events for sample rate updates
        self._event_bus.subscribe(EventType.STATUS_UPDATE, self._on_status_update)
        self._event_bus.subscribe(EventType.DATA_SENT, self._on_data_sent)
        
    def start(self) -> None:
        """Start the ZMQ service in a separate thread."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._event_bus.publish_event(EventType.SERVICE_STARTED, source="ZMQService")
        
    def stop(self) -> None:
        """Stop the ZMQ service."""
        self._running = False
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=5.0)
                if self._thread.is_alive():
                    print("Warning: ZMQ thread did not terminate within timeout")
            except Exception as e:
                print(f"Error joining ZMQ thread: {e}")
        
        # Cleanup ZMQ resources
        try:
            self._cleanup()
        except Exception as e:
            print(f"Error during ZMQ cleanup: {e}")
        
        # Unsubscribe from events
        try:
            self._event_bus.unsubscribe(EventType.STATUS_UPDATE, self._on_status_update)
            self._event_bus.unsubscribe(EventType.DATA_SENT, self._on_data_sent)
        except Exception as e:
            print(f"Error unsubscribing from events: {e}")
            
        # Publish stopped event (if event bus is still working)
        try:
            self._event_bus.publish_event(EventType.SERVICE_STOPPED, source="ZMQService")
        except Exception as e:
            print(f"Error publishing service stopped event: {e}")
        
    def _init_sockets(self) -> None:
        """Initialize ZMQ sockets."""
        try:
            self.connection_status = ConnectionStatus.CONNECTING
            self._publish_status_update()
            
            self.context = zmq.Context()
            self.poller = zmq.Poller()
            
            # Data socket
            data_address = f'{self.protocol}{self.ip}:{self.data_port}'
            print(f"Connecting to data socket at {data_address}")
            self.data_socket = self.context.socket(zmq.SUB)
            self.data_socket.connect(data_address)
            self.data_socket.setsockopt(zmq.SUBSCRIBE, b'')
            self.poller.register(self.data_socket, zmq.POLLIN)
            
            # Heartbeat socket
            heartbeat_address = f'{self.protocol}{self.ip}:{self.heartbeat_port}'
            print(f"Connecting to heartbeat socket at {heartbeat_address}")
            self.heartbeat_socket = self.context.socket(zmq.REQ)
            self.heartbeat_socket.connect(heartbeat_address)
            self.poller.register(self.heartbeat_socket, zmq.POLLIN)
            
            self.connection_status = ConnectionStatus.CONNECTED
            self._publish_status_update()
            
        except Exception as e:
            self.connection_status = ConnectionStatus.NOT_CONNECTED
            self._event_bus.publish_event(
                EventType.ZMQ_CONNECTION_ERROR,
                data={"error": str(e), "status": self.connection_status},
                source="ZMQService"
            )
    
    def _send_heartbeat(self) -> None:
        """Send heartbeat to OpenEphys server."""
        if not self.heartbeat_socket:
            return
            
        heartbeat_data = {
            'application': self.app_name,
            'uuid': self.uuid,
            'type': 'heartbeat'
        }
        json_msg = json.dumps(heartbeat_data)
        
        try:
            self.heartbeat_socket.send(json_msg.encode('utf-8'))
            self.last_heartbeat_timestamp = time.time()
            self.socket_waits_reply = True
        except zmq.ZMQError as e:
            self._event_bus.publish_event(
                EventType.ZMQ_CONNECTION_ERROR,
                data={"error": f"Heartbeat send failed: {e}"},
                source="ZMQService"
            )
    
    def _handle_heartbeat_timeout(self) -> None:
        """Handle heartbeat timeout scenarios."""
        current_time = time.time()
        
        if (current_time - self.last_heartbeat_timestamp) > self.heartbeat_timeout_duration:
            if self.socket_waits_reply:
                self.connection_status = ConnectionStatus.NOT_RESPONDING
                self._publish_status_update()
                print("Heartbeat hasn't got reply, retrying...")
                self.last_heartbeat_timestamp += 1.0
                
                if (current_time - self.last_reply_timestamp) > self.not_responding_timeout_duration:
                    self.connection_status = ConnectionStatus.RECONNECTING
                    self._publish_status_update()
                    print("Connection lost, trying to reconnect...")
                    self._reconnect()
            else:
                self._send_heartbeat()
    
    def _handle_data_timeout(self) -> None:
        """Handle data timeout scenarios."""
        if self.data_manager.check_timeout():
            timeout_status = self.data_manager.get_timeout_status()
            
            if self.data_manager.auto_reinit_enabled:
                # Perform automatic reinit
                previous_state = self.data_manager.reinit_for_new_setup()
                
                # Reset chunk delay tracking
                self._last_chunk_samples = 0
                self._chunk_delay_ms = 0.0
                
                self._event_bus.publish_event(
                    EventType.STATUS_UPDATE,
                    data={
                        "type": "auto_reinit_completed",
                        "previous_channels": previous_state["total_channels"],
                        "timeout_seconds": timeout_status["timeout_seconds"]
                    },
                    source="ZMQService"
                )
                print(f"Auto-reinit: {previous_state['total_channels']} → 1 channel (timeout: {timeout_status['timeout_seconds']}s)")
            else:
                # Publish timeout warning for manual handling
                self._event_bus.publish_event(
                    EventType.STATUS_UPDATE,
                    data={
                        "type": "data_timeout_warning",
                        "timeout_status": timeout_status,
                        "manual_reinit_available": True
                    },
                    source="ZMQService"
                )
    
    def manual_reinit_data_manager(self) -> dict:
        """Manually reinitialize DataManager (triggered by user)."""
        previous_state = self.data_manager.reinit_for_new_setup()
        
        # Reset chunk delay tracking
        self._last_chunk_samples = 0
        self._chunk_delay_ms = 0.0
        
        self._event_bus.publish_event(
            EventType.STATUS_UPDATE,
            data={
                "type": "manual_reinit_completed",
                "previous_channels": previous_state["total_channels"]
            },
            source="ZMQService"
        )
        return previous_state
    
    def _on_status_update(self, event) -> None:
        """Handle status update events for manual reinit."""
        # Prevent infinite recursion - only handle events from other sources
        if event.source == "ZMQService":
            return
            
        if event.data and event.data.get("type") == "execute_manual_reinit":
            # Always allow manual reinit when requested by user
            self.manual_reinit_data_manager()
    
    def _on_data_sent(self, event) -> None:
        """Handle data sent events to update estimated sample rate."""
        if event.data and "calculated_sample_rate" in event.data:
            sample_rate = event.data.get("calculated_sample_rate", 30000.0)
            if sample_rate > 0:
                self._estimated_sample_rate = sample_rate
    
    def _reconnect(self) -> None:
        """Reconnect to OpenEphys server."""
        try:
            if self.data_socket and self.poller:
                self.poller.unregister(self.data_socket)
                self.data_socket.close()
                self.data_socket = None
            
            self._init_sockets()
            self.socket_waits_reply = False
            self.last_reply_timestamp = time.time()
        except Exception as e:
            self._event_bus.publish_event(
                EventType.ZMQ_CONNECTION_ERROR,
                data={"error": f"Reconnection failed: {e}"},
                source="ZMQService"
            )
    
    def _handle_data_message(self, message: list) -> None:
        """Process received data message."""
        try:
            if len(message) < 2:
                print("No frames for message:", message[0])
                return
                
            header = json.loads(message[1].decode('utf-8'))
            
            if header['message_num'] != self.message_num + 1:
                print("Missed a message at number", self.message_num + 1)
            
            self.message_num = header['message_num']
            
            if header['type'] == 'data':
                self._process_data_frame(header, message)
            elif header['type'] == 'event':
                self._process_event_frame(header, message)
            elif header['type'] == 'spike':
                self._process_spike_frame(header, message)
            else:
                print("Unknown message type:", header['type'])
                
        except (ValueError, KeyError) as e:
            print(f"Error processing message: {e}")
            if len(message) > 1:
                print("Message content:", message[1])
    
    def _process_data_frame(self, header: dict, message: list) -> None:
        """Process data frame from OpenEphys with dynamic channel discovery."""
        try:
            content = header['content']
            channel_num = content['channel_num']
            channel_name = content.get('channel_name', f"CH{channel_num}")
            num_samples = content['num_samples']
            
            if len(message) > 2:
                # Dynamic channel discovery and buffer expansion
                discovery_complete = self.data_manager.add_or_expand_channel(
                    channel_num, channel_name
                )
                
                # If discovery just completed, publish status update
                if discovery_complete:
                    discovery_status = self.data_manager.get_discovery_status()
                    self._event_bus.publish_event(
                        EventType.STATUS_UPDATE,
                        data={
                            "type": "channel_discovery_complete",
                            "total_channels": discovery_status["total_channels"],
                            "discovered_channels": discovery_status["discovered_channels"],
                            "channel_info": self.data_manager.get_channel_info_all()
                        },
                        source="ZMQService"
                    )
                
                # Process and buffer the data
                n_arr = np.frombuffer(message[2], dtype=np.float32)
                self.data_manager.push_data(channel_num, n_arr.reshape(-1, num_samples))
                
                # Calculate chunk delay (how much delay one data chunk represents)
                self._last_chunk_samples = num_samples
                if self._estimated_sample_rate > 0:
                    self._chunk_delay_ms = (num_samples / self._estimated_sample_rate) * 1000.0
                
                # Publish data received event (less frequent to avoid UI spam)
                self._event_bus.publish_event(
                    EventType.DATA_RECEIVED,
                    data={
                        "channel_num": channel_num,
                        "channel_name": channel_name,
                        "num_samples": num_samples,
                        "discovery_status": self.data_manager.get_discovery_status(),
                        "chunk_delay_ms": self._chunk_delay_ms
                    },
                    source="ZMQService"
                )
                
                # Process data only after discovery is complete
                if self.data_manager.has_data_ready(min_samples=1):
                    self._process_buffered_data()
                    
        except (IndexError, ValueError) as e:
            print(f"Error processing data frame: {e}")
    
    def _process_buffered_data(self) -> None:
        """Process buffered data when ready."""
        try:
            samples_to_pop = self.data_manager.lowest_tail_index
            datalist = self.data_manager.pop_data_all_channels(samples_to_pop)
            
            # Publish processed data event
            self._event_bus.publish_event(
                EventType.DATA_PROCESSED,
                data={
                    "datalist": datalist,
                    "num_samples": samples_to_pop,
                    "num_channels": len(datalist),
                    "chunk_delay_ms": self._chunk_delay_ms
                },
                source="ZMQService"
            )
            
        except Exception as e:
            print(f"Error processing buffered data: {e}")
    
    def _process_event_frame(self, header: dict, message: list) -> None:
        """Process event frame from OpenEphys."""
        try:
            if header['data_size'] > 0 and len(message) > 2:
                event = OpenEphysEventObject(header['content'], message[2])
            else:
                event = OpenEphysEventObject(header['content'])
            print("Event received:", event)
        except Exception as e:
            print(f"Error processing event frame: {e}")
    
    def _process_spike_frame(self, header: dict, message: list) -> None:
        """Process spike frame from OpenEphys."""
        try:
            if len(message) > 2:
                spike = OpenEphysSpikeObject(header['spike'], message[2])
            else:
                spike = OpenEphysSpikeObject(header['spike'])
            print("Spike received:", spike)
        except Exception as e:
            print(f"Error processing spike frame: {e}")
    
    def _handle_heartbeat_reply(self) -> None:
        """Handle heartbeat reply from server."""
        try:
            if self.heartbeat_socket:
                message = self.heartbeat_socket.recv()
                self.connection_status = ConnectionStatus.ONLINE
                self._publish_status_update()
                
                if self.socket_waits_reply:
                    self.socket_waits_reply = False
                    self.last_reply_timestamp = time.time()
                else:
                    print("Received reply before sending a message?")
        except zmq.ZMQError as e:
            print(f"Error receiving heartbeat reply: {e}")
    
    def _publish_status_update(self) -> None:
        """Publish connection status update."""
        status_data = {
            "connection_status": self.connection_status.value,
            "ip": self.ip,
            "data_port": self.data_port,
            "heartbeat_port": self.heartbeat_port,
            "app_name": self.app_name,
            "uuid": self.uuid,
            "message_num": self.message_num
        }
        
        self._event_bus.publish_event(
            EventType.ZMQ_CONNECTION_STATUS,
            data=status_data,
            source="ZMQService"
        )
    
    def _run(self) -> None:
        """Main service loop."""
        self._init_sockets()
        
        while self._running:
            try:
                self._handle_heartbeat_timeout()
                self._handle_data_timeout()
                
                if not self.poller:
                    time.sleep(0.1)
                    continue
                    
                sockets = dict(self.poller.poll(1))
                
                if self.data_socket in sockets:
                    try:
                        message = self.data_socket.recv_multipart(zmq.NOBLOCK)
                        if message:
                            self._handle_data_message(message)
                    except zmq.ZMQError as e:
                        print(f"ZMQ data socket error: {e}")
                        break
                
                if self.heartbeat_socket in sockets and self.socket_waits_reply:
                    self._handle_heartbeat_reply()
                    
            except Exception as e:
                print(f"Error in ZMQ service loop: {e}")
                time.sleep(0.1)
        
        self._cleanup()
    
    def _cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Unregister sockets from poller first
            if self.poller:
                try:
                    if self.data_socket:
                        self.poller.unregister(self.data_socket)
                except Exception as e:
                    print(f"Error unregistering data socket: {e}")
                try:
                    if self.heartbeat_socket:
                        self.poller.unregister(self.heartbeat_socket)
                except Exception as e:
                    print(f"Error unregistering heartbeat socket: {e}")
            
            # Close sockets with proper linger settings
            if self.data_socket:
                try:
                    # Set linger to 0 to avoid blocking on close
                    self.data_socket.setsockopt(zmq.LINGER, 0)
                    self.data_socket.close()
                except Exception as e:
                    print(f"Error closing data socket: {e}")
            if self.heartbeat_socket:
                try:
                    # Set linger to 0 to avoid blocking on close  
                    self.heartbeat_socket.setsockopt(zmq.LINGER, 0)
                    self.heartbeat_socket.close()
                except Exception as e:
                    print(f"Error closing heartbeat socket: {e}")
            
            # Terminate context
            if self.context:
                try:
                    self.context.term()
                except Exception as e:
                    print(f"Error terminating ZMQ context: {e}")
                    
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            self.data_socket = None
            self.heartbeat_socket = None
            self.context = None
            self.poller = None
    
    def get_status(self) -> dict:
        """Get current service status."""
        return {
            "connection_status": self.connection_status.value,
            "running": self._running,
            "ip": self.ip,
            "data_port": self.data_port,
            "heartbeat_port": self.heartbeat_port,
            "app_name": self.app_name,
            "uuid": self.uuid,
            "message_num": self.message_num,
            "num_channels": self.data_manager.num_channels
        }