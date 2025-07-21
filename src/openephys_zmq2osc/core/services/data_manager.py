import numpy as np
import time


class DataManager:
    def __init__(self):
        self.channels = []
        self.buffer_size = 30000  # 1 Second of data at 30kHz sample rate (minimal buffering)
        self.lowest_tail_index = 0  # Track the lowest tail index across all channels
        self.channel_discovery_mode = True  # True until we detect full channel set
        self.discovered_channels = set()  # Track which channels we've seen
        self.max_channel_id = -1  # Highest channel ID discovered
        
        # Timeout tracking
        self.last_data_time = time.time()  # Track when data was last received
        self.timeout_seconds = 5.0  # Default timeout period
        self.auto_reinit_enabled = False  # Whether to auto-reinit on timeout
        self.timeout_triggered = False  # Whether timeout has been triggered

    def init_empty_buffer(self, num_channels: int, num_samples: int) -> None:
        """Initialize an empty buffer for a given number of channels and samples."""
        if num_channels <= 0 or num_samples <= 0:
            raise ValueError("Number of channels and samples must be positive integers.")
        
        self.channels = [{
            "id": i,
            "label": "",
            "head_sample_number": 0,
            "tail_index": 0,
            "tail_sample_number": 0,
            # 1D buffer for each channel
            "data": np.zeros(self.buffer_size, dtype=np.float32)
        } for i in range(num_channels)]
        
        print(f"Initialized empty buffer with {num_channels} channels and {num_samples} samples per channel.")

    def push_data(self, channel_id: int, data: np.ndarray) -> None:
        """Add data to the buffer for a given channel. Data must be 1D (samples,)"""
        if channel_id < 0 or channel_id >= len(self.channels):
            raise ValueError("Invalid channel ID.")
        
        channel = self.channels[channel_id]
        tail_index = channel['tail_index']
        # Flatten data in case it's 2D (e.g., (1, N))
        data = np.asarray(data).flatten()
        num_samples = data.shape[0]
        
        if num_samples > self.buffer_size:
            raise ValueError("Data exceeds buffer size.")
        
        # Handle wrap-around for circular buffer
        end_index = tail_index + num_samples
        if end_index <= self.buffer_size:
            channel['data'][tail_index:end_index] = data
        else:
            first_part = self.buffer_size - tail_index
            channel['data'][tail_index:] = data[:first_part]
            channel['data'][:end_index % self.buffer_size] = data[first_part:]
        
        # Update tail index and head sample number
        channel['tail_index'] = (tail_index + num_samples) % self.buffer_size
        channel['tail_sample_number'] += num_samples
        self.update_lowest_tail_index()
        
        # Update data timestamp
        self.update_data_timestamp()

    def pop_data(self, channel_id: int, num_samples_to_pop: int) -> np.ndarray:
        """Remove data from the buffer for a given channel."""
        if channel_id < 0 or channel_id >= len(self.channels):
            raise ValueError("Invalid channel ID.")
        
        channel = self.channels[channel_id]
        tail_index = channel['tail_index']
        head_sample_number = channel['head_sample_number']
        tail_sample_number = channel['tail_sample_number']

        if num_samples_to_pop <= 0 or num_samples_to_pop > (tail_sample_number - head_sample_number):
            raise ValueError("Invalid number of samples to pop.")

        # Calculate the new tail index
        new_tail_index = (tail_index - num_samples_to_pop) % self.buffer_size
        popped_data = channel['data'][new_tail_index:tail_index]
        
        # Update head sample number and tail index
        channel['head_sample_number'] += num_samples_to_pop
        channel['tail_index'] = new_tail_index

        return popped_data  # single channel data
    
    def pop_data_all_channels(self, num_samples_to_pop: int) -> list[np.ndarray]:
        """Remove data from all channels."""
        if num_samples_to_pop <= 0:
            raise ValueError("Number of samples to pop must be positive.")
        
        popped_data = []
        for channel in self.channels:
            if channel['tail_sample_number'] - channel['head_sample_number'] < num_samples_to_pop:
                raise ValueError(f"Not enough data in channel {channel['id']} to pop {num_samples_to_pop} samples.")
            popped_data.append(self.pop_data(channel['id'], num_samples_to_pop))
        
        # Update the lowest tail index after popping data
        self.update_lowest_tail_index()

        return popped_data  # list of popped data for each channel
    
    def update_lowest_tail_index(self) -> None:
        """Update the lowest tail index across discovered channels only."""
        if not self.channels or not self.discovered_channels:
            self.lowest_tail_index = 0
            return
        
        # Only consider discovered channels for data readiness
        discovered_tail_indices = [
            self.channels[ch_id]['tail_index'] 
            for ch_id in self.discovered_channels 
            if ch_id < len(self.channels)
        ]
        
        if discovered_tail_indices:
            self.lowest_tail_index = min(discovered_tail_indices)
        else:
            self.lowest_tail_index = 0

    @property
    def num_channels(self) -> int:
        """Get the number of channels."""
        return len(self.channels)
    
    def get_channel_info(self, channel_id: int) -> dict:
        """Get information about a specific channel."""
        if channel_id < 0 or channel_id >= len(self.channels):
            raise ValueError("Invalid channel ID.")
        return self.channels[channel_id].copy()
    
    def has_data_ready(self, min_samples: int = 1) -> bool:
        """Check if we have minimum samples ready across all channels."""
        if not self.channels:
            return False
        # Don't send data during channel discovery phase
        if self.channel_discovery_mode:
            return False
        return self.lowest_tail_index >= min_samples

    def add_or_expand_channel(self, channel_id: int, channel_name: str = None) -> bool:
        """
        Add a new channel or expand buffer if needed.
        Returns True if this completes channel discovery.
        """
        # Track discovered channels
        if channel_id in self.discovered_channels:
            # Channel repeat detected - discovery complete!
            if self.channel_discovery_mode:
                print(f"Channel discovery complete! Detected {len(self.discovered_channels)} channels.")
                self.channel_discovery_mode = False
                return True
            return False
        
        # New channel discovered
        self.discovered_channels.add(channel_id)
        self.max_channel_id = max(self.max_channel_id, channel_id)
        
        # Expand buffer if needed
        required_channels = self.max_channel_id + 1  # 0-indexed
        while len(self.channels) < required_channels:
            new_id = len(self.channels)
            self.channels.append({
                "id": new_id,
                "label": f"CH{new_id:03d}",  # Default label
                "head_sample_number": 0,
                "tail_index": 0,
                "tail_sample_number": 0,
                "data": np.zeros(self.buffer_size, dtype=np.float32)
            })
        
        # Update channel name if provided
        if channel_name and channel_id < len(self.channels):
            self.channels[channel_id]["label"] = channel_name
            
        print(f"Discovered channel {channel_id} ({channel_name or f'CH{channel_id:03d}'}). Total: {len(self.discovered_channels)} channels")
        return False

    def get_discovery_status(self) -> dict:
        """Get current channel discovery status."""
        return {
            "discovery_mode": self.channel_discovery_mode,
            "discovered_channels": sorted(list(self.discovered_channels)),
            "total_channels": len(self.discovered_channels),
            "max_channel_id": self.max_channel_id,
            "buffer_channels": len(self.channels)
        }

    def get_channel_info_all(self) -> list:
        """Get information about all channels."""
        return [
            {
                "id": ch["id"],
                "label": ch["label"],
                "tail_samples": ch["tail_sample_number"],
                "discovered": ch["id"] in self.discovered_channels
            }
            for ch in self.channels
        ]

    def configure_timeout(self, timeout_seconds: float, auto_reinit: bool = False) -> None:
        """Configure timeout settings."""
        self.timeout_seconds = timeout_seconds
        self.auto_reinit_enabled = auto_reinit
        self.timeout_triggered = False  # Reset timeout flag

    def update_data_timestamp(self) -> None:
        """Update the last data received timestamp."""
        self.last_data_time = time.time()
        self.timeout_triggered = False  # Reset timeout when new data arrives

    def check_timeout(self) -> bool:
        """
        Check if data timeout has been reached.
        Returns True if timeout occurred (first time only).
        """
        if self.timeout_triggered:
            return False  # Already handled
            
        current_time = time.time()
        time_since_data = current_time - self.last_data_time
        
        if time_since_data >= self.timeout_seconds:
            self.timeout_triggered = True
            return True
            
        return False

    def get_timeout_status(self) -> dict:
        """Get current timeout status information."""
        current_time = time.time()
        time_since_data = current_time - self.last_data_time
        
        return {
            "timeout_seconds": self.timeout_seconds,
            "time_since_data": time_since_data,
            "timeout_triggered": self.timeout_triggered,
            "auto_reinit_enabled": self.auto_reinit_enabled,
            "can_manual_reinit": not self.is_receiving_data(),
            "time_until_timeout": max(0, self.timeout_seconds - time_since_data)
        }

    def is_receiving_data(self) -> bool:
        """Check if data is currently being received (within last 1 second)."""
        return (time.time() - self.last_data_time) < 1.0

    def reinit_for_new_setup(self) -> dict:
        """
        Reinitialize the DataManager for a new channel setup.
        Returns previous state information.
        """
        previous_state = {
            "discovered_channels": list(self.discovered_channels),
            "total_channels": len(self.discovered_channels),
            "buffer_channels": len(self.channels)
        }
        
        # Reset to initial state
        self.channels = []
        self.discovered_channels = set()
        self.max_channel_id = -1
        self.channel_discovery_mode = True
        self.lowest_tail_index = 0
        self.timeout_triggered = False
        self.last_data_time = time.time()
        
        # Reinitialize with minimal buffer
        self.init_empty_buffer(num_channels=1, num_samples=self.buffer_size)
        
        print(f"DataManager reinitialized: {previous_state['total_channels']} → 1 channel")
        return previous_state