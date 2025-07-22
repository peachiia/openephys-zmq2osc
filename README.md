# OpenEphys ZMQ to OSC Bridge

A high-performance, real-time data bridge for neuroscience applications. Receives neural data streams from OpenEphys GUI via ZMQ and forwards them to creative applications using OSC protocol.

**Designed for artists, researchers, and creative technologists** working with real-time neural data in interactive art, performance, and research setups.

## Features

- **High-Performance Data Processing** - Handles 32+ channels at 30kHz with optimized batching
- **Real-Time Monitoring** - Rich terminal interface with live performance metrics
- **Cross-Platform Distribution** - Single-file executables for Linux, macOS, and Windows
- **Flexible Configuration** - JSON-based config with performance presets
- **Artist-Friendly** - Zero-setup binaries ready for creative applications

## Quick Start

### Download

Get the latest binary for your platform from the [releases page]:

- **Linux (x64)**: `openephys-zmq2osc-linux-x64`
- **macOS (Apple Silicon)**: `openephys-zmq2osc-darwin-arm64`  
- **macOS (Intel)**: `openephys-zmq2osc-darwin-x64`
- **Windows (x64)**: `openephys-zmq2osc-windows-x64.exe`

### Basic Usage

```bash
# Make executable (macOS/Linux)
chmod +x openephys-zmq2osc-*

# Create default configuration
./openephys-zmq2osc --create-config

# Run with default settings
./openephys-zmq2osc

# Run with high-throughput preset
./openephys-zmq2osc --config config_high_throughput.json
```

## Configuration

### Quick Setup Presets

Generate optimized configurations for different use cases:

```bash
# High-throughput mode (32+ channels)
./openephys-zmq2osc --create-config --preset high_throughput

# Low-latency mode (1-16 channels)  
./openephys-zmq2osc --create-config --preset low_latency
```

### Manual Configuration

**Basic connection settings:**

```json
{
  "zmq": {
    "host": "localhost",
    "data_port": 5556,
    "auto_reinit_on_timeout": true
  },
  "osc": {
    "host": "127.0.0.1", 
    "port": 10000,
    "base_address": "/data",
    "processing": {
      "downsampling_factor": 30,
      "downsampling_method": "average",
      "batch_size": 1
    }
  }
}
```

**Performance optimization:**

```json
{
  "performance": {
    "osc_batch_size": 50,
    "osc_queue_max_size": 100,
    "osc_queue_overflow_strategy": "drop_oldest",
    "enable_batching": true,
    "mode": "high_throughput"
  }
}
```

## OpenEphys Setup

1. **Add ZMQ Interface Plugin** to your signal chain in OpenEphys GUI
2. **Configure ports:**
   - Data Port: `5556`
   - Heartbeat Port: `5557` (auto-assigned)
3. **Start recording** in OpenEphys
4. **Launch bridge** to begin data forwarding

## OSC Data Formats

### Sample Mode (Default)
- **Address:** `/data/sample`
- **Format:** `[ch0, ch1, ch2, ..., ch31]`
- **Rate:** Configurable downsampling (1x to 100x reduction)

### Batch Mode (High-Throughput)
- **Address:** `/data/chunk`
- **Format:** `[timestamp, samples, channels, ...data...]`
- **Rate:** Reduced message count via batching

## Performance Modes

### High-Throughput (32+ Channels)
```json
{
  "osc": {
    "processing": {
      "downsampling_factor": 30,
      "batch_size": 50
    }
  },
  "performance": {
    "mode": "high_throughput",
    "enable_batching": true
  }
}
```

**Results:** 48x reduction in OSC messages, stable with 64+ channels

### Low-Latency (1-16 Channels)
```json
{
  "osc": {
    "processing": {
      "downsampling_factor": 1,
      "batch_size": 1
    }
  },
  "performance": {
    "mode": "low_latency",
    "enable_batching": false
  }
}
```

**Results:** Minimal latency, individual sample processing

## Creative Application Examples

### Max/MSP
```max
[udpreceive 10000]
|
[route /data/sample]
|
[unpack f f f f f f f f] // 8 channels shown
```

### TouchDesigner
1. Add **OSC In DAT**
2. Set **Port** to `10000`
3. Set **Address Filter** to `/data/*`
4. Neural data appears as arrays

### Pure Data
```pd
[netreceive 10000 1]
|
[route /data/sample]
|
[unpack f f f f] // Unpack desired channels
```

## Command Line Reference

```bash
openephys-zmq2osc [OPTIONS]

Options:
  --config FILE           Configuration file (default: config.json)
  --create-config        Generate sample configuration
  --preset MODE          Preset: low_latency, balanced, high_throughput
  --zmq-host HOST        OpenEphys server IP
  --zmq-port PORT        OpenEphys ZMQ port
  --osc-host HOST        OSC destination IP  
  --osc-port PORT        OSC destination port
  --version, -v          Show version
  --help, -h             Show help
```

## Performance Monitoring

The terminal interface displays real-time performance metrics:

```
Data Flow      ✓ ACTIVE | Channels: 32 | Rate: 30000.0 Hz
Messages    Sent: 15360 | OSC: 307 | Batch: 50 (50.0x efficiency)
Queue       Used: 12/100 | Overflows: 0 | Dropped: 0
Processing     Downsampling: 30:1 | Method: Average
```

## Troubleshooting

### High CPU Usage
- Enable batching: `"enable_batching": true`
- Increase batch size: `"osc_batch_size": 50`
- Reduce UI refresh rate: `"refresh_rate": 5`

### Data Dropouts
- Increase queue size: `"osc_queue_max_size": 200`
- Use `drop_oldest` overflow strategy
- Check network bandwidth

### Connection Issues
- Verify OpenEphys ZMQ plugin configuration
- Check firewall settings
- Try IP `127.0.0.1` instead of `localhost`

## Development

For developers working with the source code:

```bash
# Install with uv package manager
uv sync

# Run from source  
uv run python -m openephys_zmq2osc.main

# Run tests
uv run pytest

# Build binary
uv run python build.py
```

See `CLAUDE.md` for detailed development guidelines and architecture documentation.

## License

MIT License - see LICENSE file for details.

## Support

- **Issues:** [GitHub Issues](https://github.com/your-username/openephys-zmq2osc/issues)
- **Documentation:** See `CLAUDE.md` for technical details
- **Community:** [Discussions](https://github.com/your-username/openephys-zmq2osc/discussions)

---

**Ready for Production** - Download, configure, and start streaming neural data to your creative applications in minutes!