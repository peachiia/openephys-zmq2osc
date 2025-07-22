"""Unified data processing for downsampling and batching neural data."""

import time

import numpy as np


class DownsamplingBuffer:
    """Stage 1: Buffer for accumulating samples for downsampling."""

    def __init__(self, num_channels: int, downsampling_factor: int, method: str = "average"):
        self.num_channels = num_channels
        self.downsampling_factor = downsampling_factor
        self.method = method

        # Initialize buffer to accumulate samples
        self.sample_buffer = np.zeros((downsampling_factor, num_channels), dtype=np.float32)
        self.buffer_position = 0
        self.samples_accumulated = 0

    def add_samples(self, samples: np.ndarray) -> list[np.ndarray]:
        """Add samples and return downsampled results when buffer is full."""
        if samples.size == 0:
            return []

        # Ensure samples are 2D (num_samples, num_channels)
        if samples.ndim == 1:
            samples = samples.reshape(1, -1)
        elif samples.ndim == 2 and samples.shape[0] == self.num_channels:
            samples = samples.T

        downsampled_results = []

        for sample in samples:
            self.sample_buffer[self.buffer_position] = sample
            self.buffer_position += 1
            self.samples_accumulated += 1

            # Check if buffer is full
            if self.buffer_position >= self.downsampling_factor:
                # Perform downsampling
                if self.method == "average":
                    downsampled = np.mean(self.sample_buffer, axis=0)
                elif self.method == "decimate":
                    downsampled = self.sample_buffer[-1]
                else:
                    downsampled = np.mean(self.sample_buffer, axis=0)

                downsampled_results.append(downsampled)
                self.buffer_position = 0

        return downsampled_results

    def reset(self) -> None:
        """Reset the downsampling buffer."""
        self.sample_buffer.fill(0)
        self.buffer_position = 0
        self.samples_accumulated = 0

    def get_status(self) -> dict:
        """Get buffer status for monitoring."""
        return {
            "buffer_position": self.buffer_position,
            "downsampling_factor": self.downsampling_factor,
            "samples_accumulated": self.samples_accumulated,
            "buffer_fill_percent": (self.buffer_position / self.downsampling_factor) * 100,
            "method": self.method,
        }


class BatchingBuffer:
    """Stage 2: Buffer for accumulating downsampled samples for batching."""

    def __init__(self, num_channels: int, batch_size: int, batch_timeout_ms: float = 10.0):
        self.num_channels = num_channels
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms

        # Buffer to accumulate downsampled samples
        self.sample_buffer: list[np.ndarray] = []
        self.last_batch_time = time.time()

    def add_samples(self, samples: list[np.ndarray]) -> list[dict]:
        """Add downsampled samples and return batches when ready."""
        batches_ready = []

        for sample in samples:
            self.sample_buffer.append(sample)

            # Check if we have enough samples for a batch
            if len(self.sample_buffer) >= self.batch_size:
                batch_data = self.sample_buffer[:self.batch_size]
                self.sample_buffer = self.sample_buffer[self.batch_size:]
                batches_ready.append(self._create_batch_dict(batch_data))
                self.last_batch_time = time.time()

        # Check for timeout-based batch sending
        current_time = time.time()
        if (self.sample_buffer and
            (current_time - self.last_batch_time) * 1000 >= self.batch_timeout_ms):
            batch_data = self.sample_buffer.copy()
            self.sample_buffer.clear()
            batches_ready.append(self._create_batch_dict(batch_data))
            self.last_batch_time = current_time

        return batches_ready

    def _create_batch_dict(self, batch_data: list[np.ndarray]) -> dict:
        """Create batch dictionary with flattened data organized by channel."""
        chunk_size = len(batch_data)

        # Flatten data by channel: [ch1_sample1, ch1_sample2, ..., ch2_sample1, ch2_sample2, ...]
        flattened_data = []
        for ch_idx in range(self.num_channels):
            for sample in batch_data:
                flattened_data.append(float(sample[ch_idx]))

        return {
            "chunk_size": chunk_size,
            "num_channels": self.num_channels,
            "flattened_data": flattened_data
        }

    def flush_pending(self) -> dict | None:
        """Flush any pending samples as a partial batch."""
        if self.sample_buffer:
            batch_data = self.sample_buffer.copy()
            self.sample_buffer.clear()
            self.last_batch_time = time.time()
            return self._create_batch_dict(batch_data)
        return None

    def reset(self) -> None:
        """Reset the batching buffer."""
        self.sample_buffer.clear()
        self.last_batch_time = time.time()

    def get_status(self) -> dict:
        """Get buffer status for monitoring."""
        return {
            "samples_in_buffer": len(self.sample_buffer),
            "batch_size": self.batch_size,
            "batch_timeout_ms": self.batch_timeout_ms,
            "buffer_fill_percent": (len(self.sample_buffer) / self.batch_size) * 100,
        }


class DataProcessor:
    """Unified two-stage data processor: downsampling → batching → OSC ready data."""

    def __init__(self, config=None):
        self.config = config
        self.num_channels = 0

        # Processing stages
        self.downsampling_buffer: DownsamplingBuffer | None = None
        self.batching_buffer: BatchingBuffer | None = None

        # Configuration
        self.downsampling_factor = 1
        self.downsampling_method = "average"
        self.batch_size = 1
        self.batch_timeout_ms = 10.0

        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from config object."""
        if not self.config or not hasattr(self.config, "osc"):
            return

        osc_config = self.config.osc

        # Try new unified config structure first
        if hasattr(osc_config, "processing"):
            processing = osc_config.processing
            self.downsampling_factor = getattr(processing, "downsampling_factor", 1)
            self.downsampling_method = getattr(processing, "downsampling_method", "average")
            self.batch_size = getattr(processing, "batch_size", 1)
            self.batch_timeout_ms = getattr(processing, "batch_timeout_ms", 10.0)
        else:
            # Fallback to old config structure
            self.downsampling_factor = getattr(osc_config, "downsampling_factor", 1)
            self.downsampling_method = getattr(osc_config, "downsampling_method", "average")

            # Get batch size from performance config if available
            if hasattr(self.config, "performance"):
                perf = self.config.performance
                self.batch_size = getattr(perf, "osc_batch_size", 1)

    def initialize(self, num_channels: int) -> None:
        """Initialize the processor with channel count."""
        self.num_channels = num_channels

        # Initialize downsampling stage
        if self.downsampling_factor > 1:
            self.downsampling_buffer = DownsamplingBuffer(
                num_channels=num_channels,
                downsampling_factor=self.downsampling_factor,
                method=self.downsampling_method
            )

        # Initialize batching stage
        if self.batch_size > 1:
            self.batching_buffer = BatchingBuffer(
                num_channels=num_channels,
                batch_size=self.batch_size,
                batch_timeout_ms=self.batch_timeout_ms
            )

    def process_datalist(self, datalist: list[np.ndarray]) -> list[dict]:
        """
        Process datalist from ZMQ service through the two-stage pipeline.
        
        Args:
            datalist: List of numpy arrays, one per channel (from ZMQ service)
            
        Returns:
            List of batch dictionaries ready for OSC transmission
        """
        if not datalist or len(datalist) == 0:
            return []

        # Convert datalist to transposed format (samples, channels)
        data_array = np.array(datalist)
        transposed_data = data_array.T  # Shape: (num_samples, num_channels)

        # Stage 1: Downsampling
        if self.downsampling_buffer:
            downsampled_samples = self.downsampling_buffer.add_samples(transposed_data)
        else:
            # No downsampling - convert to list of samples
            downsampled_samples = [sample for sample in transposed_data]

        # Stage 2: Batching
        if self.batching_buffer:
            return self.batching_buffer.add_samples(downsampled_samples)
        else:
            # No batching - create individual batches
            batches = []
            for sample in downsampled_samples:
                batches.append({
                    "chunk_size": 1,
                    "num_channels": self.num_channels,
                    "flattened_data": [float(x) for x in sample]
                })
            return batches

    def flush_pending(self) -> list[dict]:
        """Flush any pending data from buffers."""
        batches = []

        if self.batching_buffer:
            pending_batch = self.batching_buffer.flush_pending()
            if pending_batch:
                batches.append(pending_batch)

        return batches

    def reset(self) -> None:
        """Reset all processing stages."""
        if self.downsampling_buffer:
            self.downsampling_buffer.reset()
        if self.batching_buffer:
            self.batching_buffer.reset()

    def get_effective_sample_rate(self, original_rate: float) -> float:
        """Get the effective sample rate after downsampling."""
        return original_rate / self.downsampling_factor

    def get_status(self) -> dict:
        """Get comprehensive processor status."""
        status = {
            "downsampling_factor": self.downsampling_factor,
            "downsampling_method": self.downsampling_method,
            "batch_size": self.batch_size,
            "batch_timeout_ms": self.batch_timeout_ms,
            "num_channels": self.num_channels,
            "downsampling_enabled": self.downsampling_factor > 1,
            "batching_enabled": self.batch_size > 1,
        }

        if self.downsampling_buffer:
            status["downsampling_buffer"] = self.downsampling_buffer.get_status()

        if self.batching_buffer:
            status["batching_buffer"] = self.batching_buffer.get_status()

        return status


def validate_processing_config(
    downsampling_factor: int,
    method: str,
    batch_size: int,
    batch_timeout_ms: float
) -> tuple[bool, str]:
    """Validate all processing configuration parameters."""

    # Validate downsampling
    if not isinstance(downsampling_factor, int) or downsampling_factor < 1:
        return False, "Downsampling factor must be a positive integer"

    if downsampling_factor > 1000:
        return False, "Downsampling factor too large (max 1000)"

    valid_methods = ["average", "decimate"]
    if method not in valid_methods:
        return False, f"Invalid downsampling method '{method}'. Valid options: {valid_methods}"

    # Validate batching
    if not isinstance(batch_size, int) or batch_size < 1:
        return False, "Batch size must be a positive integer"

    if batch_size > 1000:
        return False, "Batch size too large (max 1000)"

    if not isinstance(batch_timeout_ms, (int, float)) or batch_timeout_ms <= 0:
        return False, "Batch timeout must be a positive number"

    return True, ""
