"""Signal processing utilities for data downsampling and filtering."""

import numpy as np
from typing import List, Optional, Tuple
import time


class DownsamplerBuffer:
    """Buffer for accumulating samples for downsampling."""
    
    def __init__(self, num_channels: int, downsampling_factor: int, method: str = "average"):
        self.num_channels = num_channels
        self.downsampling_factor = downsampling_factor
        self.method = method
        
        # Initialize buffer to accumulate samples
        self.sample_buffer = np.zeros((downsampling_factor, num_channels), dtype=np.float32)
        self.buffer_position = 0
        self.samples_accumulated = 0
        
        # Track timing for sample rate calculation
        self.last_downsample_time = time.time()
        
    def add_samples(self, samples: np.ndarray) -> List[np.ndarray]:
        """
        Add samples to buffer and return downsampled samples when ready.
        
        Args:
            samples: Shape (num_samples, num_channels)
            
        Returns:
            List of downsampled sample arrays, each shape (num_channels,)
        """
        if samples.size == 0:
            return []
            
        # Ensure samples are 2D (num_samples, num_channels)
        if samples.ndim == 1:
            # Single sample across channels
            samples = samples.reshape(1, -1)
        elif samples.ndim == 2 and samples.shape[0] == self.num_channels:
            # Transpose if shape is (channels, samples)
            samples = samples.T
            
        downsampled_results = []
        
        for sample in samples:
            # Add sample to buffer
            self.sample_buffer[self.buffer_position] = sample
            self.buffer_position += 1
            self.samples_accumulated += 1
            
            # Check if buffer is full
            if self.buffer_position >= self.downsampling_factor:
                # Perform downsampling
                if self.method == "average":
                    downsampled = np.mean(self.sample_buffer, axis=0)
                elif self.method == "decimate":
                    # Take every Nth sample (last sample in buffer)
                    downsampled = self.sample_buffer[-1]
                else:
                    # Default to average
                    downsampled = np.mean(self.sample_buffer, axis=0)
                
                downsampled_results.append(downsampled)
                
                # Reset buffer
                self.buffer_position = 0
                self.last_downsample_time = time.time()
                
        return downsampled_results
    
    def get_effective_sample_rate(self, original_rate: float) -> float:
        """Calculate the effective sample rate after downsampling."""
        return original_rate / self.downsampling_factor
    
    def reset(self) -> None:
        """Reset the downsampler buffer."""
        self.sample_buffer.fill(0)
        self.buffer_position = 0
        self.samples_accumulated = 0
        self.last_downsample_time = time.time()
    
    def get_buffer_status(self) -> dict:
        """Get current buffer status for monitoring."""
        return {
            "buffer_position": self.buffer_position,
            "downsampling_factor": self.downsampling_factor,
            "samples_accumulated": self.samples_accumulated,
            "buffer_fill_percent": (self.buffer_position / self.downsampling_factor) * 100,
            "method": self.method,
        }


class SignalProcessor:
    """Main signal processing class for handling downsampling."""
    
    def __init__(self, config=None):
        self.config = config
        self.downsampler: Optional[DownsamplerBuffer] = None
        self.num_channels = 0
        
        # Configuration from OSC config
        self.downsampling_factor = 1
        self.downsampling_method = "average"
        
        if config and hasattr(config, 'osc'):
            osc_config = config.osc
            self.downsampling_factor = getattr(osc_config, 'downsampling_factor', 1)
            self.downsampling_method = getattr(osc_config, 'downsampling_method', 'average')
    
    def initialize(self, num_channels: int) -> None:
        """Initialize the signal processor with channel count."""
        self.num_channels = num_channels
        
        if self.downsampling_factor > 1:
            self.downsampler = DownsamplerBuffer(
                num_channels=num_channels,
                downsampling_factor=self.downsampling_factor,
                method=self.downsampling_method
            )
    
    def process_samples(self, samples: np.ndarray) -> List[np.ndarray]:
        """
        Process incoming samples, applying downsampling if configured.
        
        Args:
            samples: Input samples, shape varies based on input format
            
        Returns:
            List of processed sample arrays for OSC transmission
        """
        if self.downsampling_factor <= 1 or self.downsampler is None:
            # No downsampling - return samples as-is
            if samples.ndim == 2:
                # Multiple samples - return list of individual samples
                return [sample for sample in samples]
            else:
                # Single sample - return as list
                return [samples]
        
        # Apply downsampling
        return self.downsampler.add_samples(samples)
    
    def reset(self) -> None:
        """Reset the signal processor state."""
        if self.downsampler:
            self.downsampler.reset()
    
    def get_effective_sample_rate(self, original_rate: float) -> float:
        """Get the effective sample rate after processing."""
        if self.downsampling_factor <= 1:
            return original_rate
        return original_rate / self.downsampling_factor
    
    def get_status(self) -> dict:
        """Get current processor status for monitoring."""
        status = {
            "downsampling_factor": self.downsampling_factor,
            "downsampling_method": self.downsampling_method,
            "num_channels": self.num_channels,
            "downsampling_enabled": self.downsampling_factor > 1,
        }
        
        if self.downsampler:
            status["buffer_status"] = self.downsampler.get_buffer_status()
        
        return status


def validate_downsampling_config(downsampling_factor: int, method: str) -> Tuple[bool, str]:
    """
    Validate downsampling configuration parameters.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(downsampling_factor, int) or downsampling_factor < 1:
        return False, "Downsampling factor must be a positive integer"
    
    if downsampling_factor > 1000:
        return False, "Downsampling factor too large (max 1000)"
    
    valid_methods = ["average", "decimate"]
    if method not in valid_methods:
        return False, f"Invalid downsampling method '{method}'. Valid options: {valid_methods}"
    
    return True, ""