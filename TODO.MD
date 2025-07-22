# TODO.md

Here's a list of instructions/prompts for a Claude AI agent, derived from the current tasks, along with a simple template for adding new tasks.

## Claude Code Agent Instructions

Use these instructions as prompts to guide your work on the project:

### Enhanced OSC Data Channels (COMPLETED ✓)

The OSC service has been redesigned to support two distinct modes for different use cases:

#### 1. Individual Sample Mode (Batching Disabled)
- **Address Format**: `/data/sample`
- **Data**: `[ch01, ch02, ch03, ..., ch32]`
- **Downsampling**: Configurable factor (1 = no downsampling, 30 = 30:1 reduction)  
- **Method**: Average or decimate
- **Use Case**: MaxMSP/TouchDesigner users who prefer individual sample messages with reduced data rate

#### 2. Chunk Batch Mode (Batching Enabled)
Two sub-formats available:

##### Timestamped Chunks (Recommended)
- **Address**: `/data/chunk`
- **Data**: `[timestamp, num_samples, num_channels, ...flattened_data...]`
- **Use Case**: Applications needing synchronization metadata

##### Simple Array Chunks
- **Address**: `/data/chunk/{samples}x{channels}`
- **Data**: `[sample1_ch1, sample1_ch2, ..., sample2_ch1, sample2_ch2, ...]`
- **Use Case**: Performance-critical applications with minimal parsing overhead

### Configuration Examples

#### High-Throughput Setup
```json
{
  "osc": {
    "downsampling_factor": 30,
    "chunk_format": "simple_array"
  },
  "performance": {
    "enable_batching": true,
    "osc_batch_size": 50
  }
}
```

#### Low-Latency Setup  
```json
{
  "osc": {
    "downsampling_factor": 10,
    "chunk_format": "timestamped"
  },
  "performance": {
    "enable_batching": false,
    "osc_batch_size": 1
  }
}
```

### Sample Configuration Files
- `config_high_throughput.json` - 30:1 downsampling, large batches, simple array format
- `config_low_latency.json` - 10:1 downsampling, individual samples, timestamped format

### Implementation Features
- ✓ Signal processing utilities with averaging and decimation
- ✓ Thread-safe downsampling buffers
- ✓ Configuration validation
- ✓ CLI status display with downsampling info
- ✓ Backward compatibility with existing configurations
- ✓ Performance optimizations for both modes

### Future Enhancements
- [ ] Add adaptive downsampling based on data rate
- [ ] Implement additional filtering methods (bandpass, etc.)
- [ ] Add compression for chunk modes
- [ ] Create configuration wizard for different use cases
- [ ] Add OSC message size monitoring
- [ ] Implement automatic fallback modes for network issues

## Template for Adding New Tasks

```markdown
- [ ] Brief description of the task
```

### Quick Reference

**Start with custom config:**
```bash
uv run python -m openephys_zmq2osc.main --config config_low_latency.json
```

**Test downsampling settings:**
```bash
uv run python -m openephys_zmq2osc.main --config config_high_throughput.json
```