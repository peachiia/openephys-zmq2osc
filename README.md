# openephys-zmq2osc

A lightweight, multithreaded CLI tool for bridging neuroscience data pipelines. It listens to neural data streams broadcasted via ZMQ from the OpenEphys GUI and forwards selected signals to downstream applications using the OSC (Open Sound Control) protocol.

**This tool is designed for artists and creative technologists** who want to use real-time neural data in interactive art and performance setups, where OSC is commonly used for controlling audiovisual elements.

## Features

- **Real-time data bridging** from OpenEphys ZMQ streams to OSC protocol
- **Rich terminal interface** with live status updates and connection monitoring  
- **Cross-platform binary distribution** - no Python installation required
- **Simple configuration** via JSON files or command-line arguments
- **Artist-friendly design** - download, configure, and run

## Quick Start

### 1. Download

Download the appropriate binary for your platform:

- **Linux**: `openephys-zmq2osc-linux-x64`
- **macOS (Apple Silicon)**: `openephys-zmq2osc-darwin-arm64`
- **macOS (Intel)**: `openephys-zmq2osc-darwin-x64`
- **Windows**: `openephys-zmq2osc-windows-x64.exe`

### 2. Make Executable (macOS/Linux only)

```bash
chmod +x openephys-zmq2osc-*
```

### 3. Run

```bash
# Run with default settings
./openephys-zmq2osc-linux-x64

# Create a configuration file first
./openephys-zmq2osc-linux-x64 --create-config
```

## Basic Usage

```bash
# Run with default settings (localhost:5556 → localhost:10000)
openephys-zmq2osc

# Create a sample configuration file
openephys-zmq2osc --create-config

# Run with custom configuration
openephys-zmq2osc --config my_config.json

# Override specific settings
openephys-zmq2osc --zmq-host 192.168.1.100 --osc-port 8000
```

### Command Line Options

```bash
openephys-zmq2osc [OPTIONS]

Options:
  -h, --help                Show help message
  --config FILE            Configuration file path (default: config.json)
  --create-config          Create a sample configuration file and exit
  --zmq-host HOST          OpenEphys server IP address
  --zmq-port PORT          OpenEphys ZMQ data port  
  --osc-host HOST          OSC destination IP address
  --osc-port PORT          OSC destination port
  --version, -v            Show version number
```

## Configuration

The application uses a JSON configuration file. Create one with:

```bash
openephys-zmq2osc --create-config
```

This creates `config.json` with these key settings:

### OpenEphys Connection (ZMQ)
```json
{
  "zmq": {
    "host": "localhost",        // OpenEphys server IP
    "data_port": 5556,         // ZMQ data port (heartbeat = port + 1)
    "num_channels": 32         // Number of neural channels
  }
}
```

### OSC Output
```json
{
  "osc": {
    "host": "127.0.0.1",           // Your application's IP
    "port": 10000,                 // Your application's OSC port
    "send_individual_channels": false,  // Send all channels together (faster)
    "base_address": "/data"        // OSC address for combined data
  }
}
```

### Display Settings

```json
{
  "ui": {
    "refresh_rate": 10,        // Terminal refresh rate (Hz)
    "show_debug_info": false   // Show debug information
  }
}
```

## OpenEphys Setup

1. **Add ZMQ Interface Plugin**
   - In OpenEphys GUI, add a **ZMQ Interface** plugin to your signal chain
   
2. **Configure the Plugin**
   - **Data Port**: 5556 (must match your config)
   - **Heartbeat Port**: 5557 (automatically data_port + 1)
   - **Application Name**: Can be anything
   
3. **Start Recording**
   - Press play in OpenEphys to start streaming data
   
4. **Run This Bridge**
   - Start `openephys-zmq2osc` to begin forwarding data

## Receiving OSC Data

The application sends neural data in two formats:

### Combined Mode (Default - Recommended)

- **OSC Address**: `/data`
- **Message Format**: Array of floats `[ch0, ch1, ch2, ..., ch31]`
- **Rate**: One message per sample (typically 30,000 Hz)

Perfect for most applications - you get all channels in one message.

### Individual Channel Mode

- **OSC Addresses**: `/ch000`, `/ch001`, `/ch002`, etc.
- **Message Format**: Single float per channel
- **Rate**: 32 messages per sample (much higher network load)

Enable by setting `"send_individual_channels": true` in config.

## Example: Receiving in Max/MSP

```max
// For combined mode (recommended)
[udpreceive 10000]
|
[route /data]
|
[unpack f f f f f f f f f f f f f f f f f f f f f f f f f f f f f f f f]
```

## Example: Receiving in Pure Data

```pd
[netreceive 10000 1]
|
[route /data]
|
[unpack f f f f f f f f f f f f f f f f f f f f f f f f f f f f f f f f]
```

## Example: Receiving in TouchDesigner

1. Add an **OSC In DAT**
2. Set **Network Port** to 10000
3. Set **Address Filter** to `/data`
4. Neural data appears as arrays in the DAT

## Troubleshooting

### Connection Issues

#### ZMQ Connection Failed

- Check that OpenEphys is running and streaming
- Verify ZMQ plugin is configured with correct ports
- Make sure firewall allows connections

#### OSC Not Receiving

- Verify your application is listening on the correct port
- Try sending to `127.0.0.1` instead of `localhost`
- Check if another application is using the OSC port

### Performance Issues

#### High CPU Usage

- Lower the UI refresh rate: `"refresh_rate": 5`
- Disable debug info: `"show_debug_info": false`

#### Choppy Data / High Latency

- Reduce buffer size in config: `"buffer_size": 150000`
- Use combined mode instead of individual channels
- Check network connection quality

#### Application Crashes

- Check config file syntax with a JSON validator
- Try creating a fresh config with `--create-config`
- Make sure OpenEphys is streaming before starting bridge

### Debug Mode

To see detailed information, edit your config file:

```json
{
  "ui": {
    "show_debug_info": true
  },
  "app": {
    "log_level": "DEBUG"
  }
}
```

## Network Setup

### Different Computers

If OpenEphys and your application are on different computers:

```bash
# OpenEphys on computer A (192.168.1.100)
# Your app on computer B (192.168.1.101)
# Run bridge on computer B:

openephys-zmq2osc --zmq-host 192.168.1.100 --osc-host 127.0.0.1
```

### Multiple Applications

To send data to multiple OSC applications, run multiple bridges:

```bash
# Send to MaxMSP on port 10000
openephys-zmq2osc --osc-port 10000 &

# Send to TouchDesigner on port 10001  
openephys-zmq2osc --osc-port 10001 &
```

## Support

- **Issues**: Report problems at [GitHub Issues]
- **Questions**: Check [Discussions] for community help
- **Documentation**: See `DEVELOPER.md` for technical details

---

**🎨 Note for Artists**: This tool is designed to be simple and reliable. The binary requires no technical setup - just download, configure, and start receiving neural data in your creative applications via OSC!
