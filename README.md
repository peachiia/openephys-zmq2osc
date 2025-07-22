# OpenEphys ZMQ to OSC Bridge

A high-performance, real-time data bridge for neuroscience applications. Receives neural data streams from OpenEphys GUI via ZMQ and forwards them to creative applications using OSC protocol. 

For the kind of creative who sees no difference between patching signals in TouchDesigner and wiring electrodes into the brain.

## Features

- **High-Performance Data Processing** - Handles 32+ channels at 30kHz with optimized batching
- **Real-Time Monitoring** - Rich terminal interface with live performance metrics
- **Cross-Platform Distribution** - Single-file executables for Linux, macOS, and Windows
- **Flexible Configuration** - JSON-based config with performance presets
- **Artist-Friendly** - (almost) Zero-setup binaries ready for creative applications

## Quick Start

### Download

Get the latest binary for your platform from the [releases page]:

- **Linux (x64)**: `openephys-zmq2osc-linux-x64`
- **macOS (Apple Silicon)**: `openephys-zmq2osc-darwin-arm64`  
- **macOS (Intel)**: `openephys-zmq2osc-darwin-x64`
- **Windows (x64)**: `openephys-zmq2osc-windows-x64.exe`

### Basic Usage

```bash
# Make executable (macOS/Linux) - Only needed once
chmod +x openephys-zmq2osc-*

# Run with default settings
./openephys-zmq2osc
```

The config.json file is automatically generated in the current directory. Any changes you make to this file will be applied the next time you run the program—no need to use the --config option. **In most cases, you won’t need to modify anything at all.**

## Configuration

### Advanced Usage

```bash
# Create default configuration file for customization
./openephys-zmq2osc --create-config

# Run with custom configuration
./openephys-zmq2osc --config config.json

# Run with high-throughput preset
./openephys-zmq2osc --config config_high_throughput.json
```

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

**To enable Sample Mode (direct channel transmission):**

Set `"enable_batching": true` in the performance configuration. This sends data to `/data/sample` with format `[ch0, ch1, ch2, ...]`. In sample mode, `batch_size` is **automatically overridden to 1** to ensure one sample per channel per message.

**To enable Batch Mode (batched transmission):**

Set `"enable_batching": false` in the performance configuration. This sends data to `/data/batch/<size>` with format `[num_channels, flattened_data]` where size is determined by the `batch_size` setting.

**Important Batching Behavior:**

- When `enable_batching=true`, the system **automatically forces** `batch_size=1` regardless of configuration
- When `enable_batching=false` but `batch_size != 1`, the UI shows **OVERRIDDEN** to indicate the system is overriding your batch_size setting
- Sample mode (`enable_batching=true`) MUST always have exactly one sample per channel to maintain /data/sample format compatibility

**Sample Mode configuration example:**

```json
{
  "osc": {
    "processing": {
      "batch_size": 1
    }
  },
  "performance": {
    "enable_batching": true
  }
}
```

**Batch Mode configuration example:**

```json
{
  "osc": {
    "processing": {
      "batch_size": 50
    }
  },
  "performance": {
    "enable_batching": false,
    "osc_queue_max_size": 100,
    "osc_queue_overflow_strategy": "drop_oldest"
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

The message format is determined by the `enable_batching` setting in the performance configuration:

### Sample Mode

- **Address:** `/data/sample`
- **Format:** `[ch0, ch1, ch2, ..., ch31]`
- **Configuration:** Set `"enable_batching": true` in performance config
- **Use Case:** Low-latency, direct channel data transmission
- **Note:** Automatically forces `batch_size=1` to ensure one sample per channel per message

### Batch Mode (Batched)

- **Address:** `/data/batch/<batch_size>`
- **Format:** `[num_channels, ch0_s1, ch1_s1, ..., ch0_s2, ch1_s2, ...]`
- **Configuration:** Set `"enable_batching": false` in performance config  
- **Use Case:** Reduced message count via batching for high-throughput scenarios
- **Note:** Uses `batch_size` to determine batch size, sends with channel count prefix

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
    "enable_batching": false
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
    "enable_batching": true
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

```text
Data Flow      ✓ ACTIVE | Channels: 32 | Rate: 30000.0 Hz
Messages    Sent: 15360 | OSC: 307 | Batch: 50 (50.0x efficiency)
Queue       Used: 12/100 | Overflows: 0 | Dropped: 0
Processing     Downsampling: 30:1 | Method: Average
```

## Troubleshooting

### High CPU Usage

- Enable batch mode: `"enable_batching": false`
- Increase batch size: `"batch_size": 50` (in osc.processing section)
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

- **Issues:** [GitHub Issues](https://github.com/peachiia/openephys-zmq2osc/issues)
- **Developer Note:** Check out CLAUDE.md for the nitty-gritty. (You know… vibe coding doesn't stop at the surface.)
- **Contributions:** Pull requests welcome! I have no idea what I’m doing, but with your AI tokens, we might just make history. : P

---

**Disclaimer** : This code is a performance piece. Bugs are part of the narrative arc. But if one ruins your scene, let me know and I’ll rewrite the script (or cry artistically, lol).
