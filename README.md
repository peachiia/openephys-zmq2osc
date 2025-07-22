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
# Create minimal configuration file (production use)
./openephys-zmq2osc --create-config

# Create full configuration file with all options (development)
./openephys-zmq2osc --create-config-dev

# Run with custom configuration
./openephys-zmq2osc --config my_config.json

# Override specific settings via command line
./openephys-zmq2osc --zmq-host 192.168.1.100 --osc-port 8000
```

### Manual Configuration

**Basic configuration (config.json):**

```json
{
  "zmq": {
    "host": "localhost",
    "data_port": 5556,
    "app_uuid": "1618"
  },
  "osc": {
    "host": "127.0.0.1",
    "port": 10000,
    "base_address": "/data",
    "processing": {
      "downsampling_factor": 30,
      "downsampling_method": "average",
      "enable_batching": true,
      "batch_size": 1
    }
  },
  "performance": {
    "osc_queue_max_size": 100,
    "osc_queue_overflow_strategy": "drop_oldest"
  }
}
```

The minimal config contains only essential settings. Use `--create-config-dev` for the full configuration with all available options.

## OpenEphys Setup

1. **Add ZMQ Interface Plugin** to your signal chain in OpenEphys GUI
2. **Configure ports:**
   - Data Port: `5556`
   - Heartbeat Port: `5557` (auto-assigned)
3. **Start recording** in OpenEphys
4. **Launch bridge** to begin data forwarding

## OSC Data Formats

The message format is determined by the `enable_batching` setting in the performance configuration (see below in section [**Performance Tuning Examples**](#performance-tuning-examples). The bridge supports two modes: **Sample Mode** and **Batch Mode**.

### Sample Mode

- **Address:** `/data/sample`
- **Format:** `[ch0, ch1, ch2, ..., ch31]`
- **Configuration:** Set `"enable_batching": false` in performance config
- **Use Case:** Low-latency, direct channel data transmission
- **Note:** Automatically forces `batch_size=1` to ensure one sample per channel per message

### Batch Mode (Batched)

- **Address:** `/data/batch`
- **Format:** `[batch_size, num_channels, ch1_s1, ch1_s2, ..., ch1_sN, ch2_s1, ...]`
- **Configuration:** Set `"enable_batching": true` in performance config  
- **Use Case:** Reduced message count via batching for high-throughput scenarios
- **Note:** Uses `batch_size` to determine batch size, sends with channel count prefix

## Performance Tuning Examples

For simple data streaming, we would recommend using sample mode with `"enable_batching": false`. This option allows the bridge to send each sample as an individual OSC message, which is suitable for low-latency applications with few channels.

```json
{
  "osc": {
    "processing": {
      "downsampling_factor": 1,
      "enable_batching": false
    }
  }
}
```

However, in some cases, especially when dealing with high-throughput scenarios (many channels, high sample rates), you may want to reduce the data rate to avoid overwhelming the network. In such cases, you can use either `downsampling_factor` or `enable batching.`

### Downsampling

To reduce the data rate, you can set a `downsampling_factor`. This will average the samples over the specified factor, effectively reducing the number of messages sent:

```json
{
  "osc": {
    "processing": {
      "downsampling_factor": 30, 
    }
  }
}
```

For example, a `downsampling_factor` of 30 means that every 30 samples will be averaged into one message, reducing the data rate by a factor of 30.

### Batching

For high-throughput scenarios, enabling batching with `"enable_batching": true` is recommended. This allows the bridge to send data in batches, reducing the number of OSC messages sent over the network. **However, this option will redirect the data to a different OSC address, so you will need to adjust your receiving application accordingly.**

```json
{
  "osc": {
    "processing": {
      "enable_batching": true,
      "batch_size": 10
    }
  }
}
```

When batching is enabled, the bridge will send messages in batches of the specified size (e.g., 10 samples per message). This can significantly reduce the number of OSC messages sent, improving performance in high-throughput scenarios.

the data will be sent to the `/data/batch/<batch_size>` address instead of `/data/sample`.

for example, if you set `"batch_size": 10` and number of channels is 32, the OSC messages will be sent to:

```text
/data/batch/10 32 0.01 0.02 0.03 ... 0.10 1.00 1.01 1.02 ... 1.10
```

when 0.01 mean `sample 1` of `channel 0`, 0.02 mean `sample 2` of `channel 0`, and so on.

### Combining Downsampling and Batching

You can also combine both downsampling and batching for optimal performance. This allows you to reduce the data rate while still sending data in batches:

```json
{
  "osc": {
    "processing": {
      "downsampling_factor": 30,
      "enable_batching": true,
      "batch_size": 10
    }
  }
}
```

In this case, the bridge will downsample the data by a factor of 30 and then send it in batches of 10 samples. The OSC messages will be sent to the `/data/batch/` address.

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
  --config FILE, -c FILE  Configuration file (default: config.json)
  --create-config         Generate minimal sample configuration
  --create-config-dev     Generate full developer configuration
  --zmq-host HOST         Override ZMQ host address
  --zmq-port PORT         Override ZMQ data port
  --osc-host HOST         Override OSC host address
  --osc-port PORT         Override OSC port
  --version, -v           Show version
  --help, -h              Show help
```

## Troubleshooting

Having issues? Don't panic! Here are common problems and their solutions, explained for both technical and non-technical users.

### The App is Running Slowly or Using Too Much Computer Resources

**What's happening:** The bridge is working too hard processing data.

**Simple fixes:**

- **Close other programs** - Free up memory by closing unnecessary applications
- **Restart both OpenEphys and the bridge** - Sometimes a fresh start fixes everything
- **Use a wired ethernet connection** instead of WiFi for better performance

**Technical adjustments (edit your config.json file):**

- Increase batch size: Set `"batch_size": 50` in the osc.processing section  

### Data is Missing or Choppy in Your Creative App

**What's happening:** The bridge can't keep up with the data flow, so some gets dropped.

**Simple fixes:**

- **Check your network connection** - Use ethernet instead of WiFi if possible
- **Move closer to your router** if using WiFi
- **Restart everything** - OpenEphys, the bridge, and your receiving application
- **Reduce the number of channels** in OpenEphys if you don't need them all

**Technical adjustments (edit your config.json file):**

- Enable downsampling: Set `"downsampling_factor": 10` or more to reduce data rate
- Increase queue size: Set `"osc_queue_max_size": 200` in the performance section

### Can't Connect to OpenEphys

**What's happening:** The bridge can't find or talk to OpenEphys GUI.

**Step-by-step fixes:**

1. **Make sure OpenEphys is actually recording** - Look for the start acquisition button (play button) to be active, clock should be running.
2. **Check the ZMQ plugin is added** - In OpenEphys, make sure "ZMQ Interface" appears in your signal chain.
3. **Verify the ZMQ Data Channel selected** - In OpenEphys, ensure the ZMQ Data Channel is selected by clicking on `Channel` box, it should show something like `32/32` which means all channels are selected (or the number of channels you have).
4. **Verify port numbers match** - The default should be 5556, check both OpenEphys and your config.json
5. **Try different IP addresses** - Change from `"localhost"` to `"127.0.0.1"` in config.json
6. **Check your firewall** - Some security software blocks these connections
7. **Run both programs as administrator/root** - This can solve permission issues

**For network connections (different computers):**

- Make sure both computers are on the same network
- Use the actual IP address instead of "localhost" (like `"192.168.1.100"`)
- Check that firewalls on both computers allow the connection

### Your Creative App (TouchDesigner/Max/etc.) Isn't Receiving Data

**What's happening:** The OSC messages aren't reaching your application.

**Technical checks:**

1. **Check the port number** - Make sure your app is listening on port 10000 (or whatever you set)
2. **Check the OSC address** - Look for `/data/sample` or `/data/batch` depending on your settings
3. **Test with a simple OSC monitor app** first to confirm data is being sent
4. **Make sure your creative app is actually running and set up correctly**

### Still Having Problems?

**Before asking for help, try this:**

1. **Restart everything** in this order: OpenEphys → Bridge → Your creative app
2. **Generate a fresh config** with `./openephys-zmq2osc --create-config`
3. **Test with minimal settings** - Use the default config first, then customize
4. **Test with a simple OSC monitor app of your choice** to see if data is being sent correctly

**Getting help:**

- Post an issue on [GitHub](https://github.com/peachiia/openephys-zmq2osc/issues)
- Include your config.json file and any error messages
- Mention your operating system and what creative software you're using

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

## License

MIT License - see LICENSE file for details.

## Support

- **Issues:** [GitHub Issues](https://github.com/peachiia/openephys-zmq2osc/issues)
- **Developer Note:** Check out CLAUDE.md for the nitty-gritty. (You know… vibe coding doesn't stop at the surface.)
- **Contributions:** Pull requests welcome! I have no idea what I’m doing, but with your AI tokens, we might just make history. : P

---

**Disclaimer** : This code is a performance piece. Bugs are part of the narrative arc. But if one ruins your scene, let me know and I’ll rewrite the script (or cry artistically, lol).
