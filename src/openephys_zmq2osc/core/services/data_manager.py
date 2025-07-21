import numpy as np


class DataManager:
    def __init__(self):
        self.channels = []
        self.buffer_size = 30000  # 1 Second of data at 30kHz sample rate (minimal buffering)
        self.lowest_tail_index = 0  # Track the lowest tail index across all channels

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
        """Update the lowest tail index across all channels."""
        if not self.channels:
            return
        self.lowest_tail_index = min(channel['tail_index'] for channel in self.channels)

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
        return self.lowest_tail_index >= min_samples