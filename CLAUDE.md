# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python CLI tool that bridges neuroscience data pipelines by listening to neural data streams from OpenEphys GUI via ZMQ and forwarding selected signals to downstream applications using OSC protocol. The primary use case is interactive art and performance setups where artists need real-time neural data.

## Architecture

The project follows a modular, event-driven architecture with clear separation between backend services and frontend interfaces:

### Core Services (`src/openephys_zmq2osc/core/`)

- **ZMQService** (`services/zmq_service.py`) - Handles OpenEphys connection, heartbeat, and data reception in separate thread
- **OSCService** (`services/osc_service.py`) - Manages OSC client and data transmission with queue-based processing  
- **DataManager** (`services/data_manager.py`) - Circular buffer system for efficient neural data storage
- **EventBus** (`events/event_bus.py`) - Thread-safe pub/sub communication between all components

### Configuration (`src/openephys_zmq2osc/config/`)

- **ConfigManager** (`settings.py`) - JSON-based configuration with hot-reload and validation
- **ProcessingConfig** - Unified processing settings (downsampling, batching) under `osc.processing`
- **PerformanceConfig** - Master switches and optimization settings including `enable_batching`
- Separate config classes for ZMQ, OSC, UI, and app settings
- Two main configuration files:
  - `config.json` - Minimal production configuration
  - `config-dev.json` - Full development configuration with all options

### Interfaces (`src/openephys_zmq2osc/interfaces/`)

- **BaseInterface** - Abstract base for pluggable UI implementations
- **CLIInterface** - Rich-based terminal interface with real-time updates via event subscriptions

### Models (`src/openephys_zmq2osc/core/models/`)

- **OpenEphys Objects** - Data structures for events, spikes, and neural data frames

## Package Management

Uses **UV** for fast, reliable dependency management:

- `pyproject.toml` - Project metadata and dependencies
- Virtual environment automatically managed by UV
- Lock file ensures reproducible builds across platforms

## Development Commands

### Running the Application

```bash
# Install dependencies and run
uv run python -m openephys_zmq2osc.main

# With custom config
uv run python -m openephys_zmq2osc.main --config my_config.json

# Override specific settings
uv run python -m openephys_zmq2osc.main --zmq-host 192.168.1.100 --osc-port 8000
```

### Development Tools

```bash
# Install development dependencies
uv add --dev pytest ruff mypy

# Code formatting and linting
uv run ruff check src/
uv run ruff format src/

# Type checking  
uv run mypy src/

# Run tests
uv run pytest
```

### Building Binaries

```bash
# Build platform-specific binary
uv run python build.py

# Test the built binary
uv run python build.py test

# Create PyInstaller spec file only
uv run python build.py spec
```

## Key Implementation Details

### Event-Driven Architecture

- All services communicate via the global EventBus using typed events
- Thread-safe with proper locks and error handling
- UI updates automatically via event subscriptions, no polling required

### Data Flow

1. **ZMQService** connects to OpenEphys, receives neural data frames
2. **DataManager** buffers data in circular arrays per channel  
3. **SignalProcessor** applies downsampling and batching based on `osc.processing` config
4. When sufficient data available, **ZMQService** publishes `DATA_PROCESSED` event
5. **OSCService** receives event, processes based on `enable_batching` setting:
   - `enable_batching=True`: Sends batched data to `/data/batch`
   - `enable_batching=False`: Forces sample mode, sends individual samples to `/data/sample`
6. **CLIInterface** updates display in real-time via status events with batch override warnings

### Threading Model

- **Main Thread**: UI rendering and event handling
- **ZMQ Thread**: OpenEphys connection and data reception  
- **OSC Thread**: Queue processing and data transmission
- All threads coordinate via EventBus with proper shutdown handling

### Configuration System

- **Dual Configuration Approach**:
  - `config.json` - Minimal production config with essential settings only
  - `config-dev.json` - Full development config with all available options
- **Unified Processing Config**: All processing settings (downsampling, batching) consolidated under `osc.processing`
- **Batching Control**: Master `enable_batching` switch in performance config
  - When `False`: Forces `batch_size=1` for sample mode (`/data/sample`)
  - When `True`: Uses configured `batch_size` for batch mode (`/data/batch`)
- JSON-based config with dataclass validation and backward compatibility
- Runtime config updates trigger service restarts
- Command-line overrides for common parameters
- Sample config generation for new users

### Binary Distribution

- PyInstaller creates single-file executables
- Cross-platform builds (macOS, Windows, Linux)
- All dependencies bundled, no Python installation required
- Platform-specific naming (e.g., `openephys-zmq2osc-linux-x64`)

## Development Guidelines & Conventions

### Markdown Best Practices (MANDATORY)

**ALWAYS follow these markdown formatting rules** to prevent markdownlint warnings:

- **MD022**: Add blank lines before and after ALL headings
- **MD031**: Add blank lines before and after ALL code blocks
- **MD032**: Add blank lines before and after ALL lists  
- **MD036**: Use proper heading levels (##, ###, ####) instead of bold text (**text**)
- **MD047**: Always end files with a single newline character
- **MD009**: Remove all trailing spaces from lines

**Example of correct formatting:**

```markdown
## Main Heading

Some text here.

### Sub Heading

- List item 1
- List item 2

Another paragraph.

```bash
code block here
```

More text.

#### Another Sub Heading

Content here.

```markdown

### Code Quality Standards

- **Formatting**: Always use `uv run ruff format src/` before commits
- **Linting**: Always use `uv run ruff check src/` and fix issues
- **Type Checking**: Run `uv run mypy src/` and address type issues
- **Testing**: Run `uv run python test_basic.py` before major changes
- **Threading**: All services must use proper thread-safe patterns via EventBus

### Configuration Management

- All runtime settings go in JSON config files
- Use dataclasses for type safety and validation
- Support command-line overrides for common settings
- Always provide sample config generation with `--create-config`

### Event-Driven Architecture Rules

- Services communicate ONLY via EventBus (no direct calls)
- All events must be typed using EventType enum
- Event handlers must be thread-safe and non-blocking
- Always unsubscribe event handlers during shutdown

### Error Handling Standards

- Log errors but don't crash services
- Use proper exception handling in all threads
- Publish error events for UI notification
- Implement graceful degradation where possible

## Future Development Tasks

### Immediate Priorities (Based on Recent Changes)

- **Configuration Migration Tool**: Automated conversion from old complex configs to new simplified format
- **Performance Preset System**: Pre-defined configs for common use cases (live performance, research, development)
- **Dynamic Batching**: Runtime adjustment of batch size based on network conditions and data rate
- **OSC Format Documentation**: Detailed docs on `/data/sample` vs `/data/batch` message formats

### High-Priority Enhancements

- **Adaptive Downsampling**: Automatically adjust based on data rate and network conditions
- **Configuration Wizard**: Interactive setup for different use cases (artist, researcher, performance)
- **OSC Message Size Monitoring**: Track and optimize network bandwidth usage with per-format metrics
- **Automatic Fallback Modes**: Handle network issues gracefully with automatic mode switching
- **Enhanced Batch Override UI**: Better visual feedback when `enable_batching=False` overrides configured batch_size

### Medium-Priority Features

- **Configuration Hot-Swapping**: Runtime config changes without service restart for processing settings
- **Multiple Processing Pipelines**: Different processing chains per channel or channel group
- **Additional Signal Processing**: Bandpass filtering, spike detection, feature extraction
- **Multiple OpenEphys Sources**: Connect to multiple GUI instances simultaneously
- **Data Recording**: Save neural data streams to file with timestamps
- **Compression**: Optional data compression for high-throughput scenarios
- **OSC Bundle Support**: Group related OSC messages into bundles for atomic delivery

### Low-Priority Extensions

- **Web-Based GUI**: Browser interface for remote monitoring and configuration
- **MIDI Output**: Convert neural signals to MIDI for music applications
- **Cloud Integration**: Stream data to cloud analytics platforms
- **Plugin Architecture**: Custom data processing modules
- **Advanced Configuration Validation**: Schema validation with detailed error messages

### Performance Optimizations

- **Memory Pool Implementation**: Eliminate allocation overhead in data paths
- **Event System Batching**: Group event publications to reduce threading overhead
- **UI Update Throttling**: Adaptive refresh rates based on system load
- **Zero-Copy Data Paths**: Minimize memory copying in high-throughput scenarios

## Development Notes for Claude Code Agent

### Architecture Quick Reference

- **Event-Driven**: All components communicate via EventBus with typed events
- **Threading**: Main (UI), ZMQ (data receive), OSC (data send), Event Bus (coordination)
- **Data Flow**: ZMQ → DataManager → SignalProcessor → Event → OSC → Network
- **Configuration**: Dual JSON approach (minimal/full) with unified processing settings

### Recent Major Changes (2024)

- **Configuration System Redesign**: Moved from multiple preset files to dual config approach
- **Processing Unification**: All processing settings (downsampling, batching) now under `osc.processing`
- **Master Batching Control**: `performance.enable_batching` controls OSC format (`/data/sample` vs `/data/batch`)
- **Automatic Override Logic**: When `enable_batching=False`, `batch_size` is forced to 1 with UI warnings
- **OSC Format Standardization**: Clear separation between sample-based and batch-based OSC messages

### Key Implementation Files

- `src/openephys_zmq2osc/core/services/osc_service.py:413-427` - OSC batching logic with enable_batching control
- `src/openephys_zmq2osc/config/settings.py:20-40` - Unified ProcessingConfig and PerformanceConfig classes
- `src/openephys_zmq2osc/core/utils/signal_processing.py:190-194` - Batch size override logic
- `src/openephys_zmq2osc/core/services/data_manager.py` - Circular buffer data management
- `src/openephys_zmq2osc/interfaces/cli_interface.py:398-401` - UI batch override warning display

### Production Readiness Status

- ✅ **Configuration System Streamlined**: Dual config approach (minimal/full) with unified processing settings
- ✅ **Batching System Enhanced**: Master `enable_batching` switch with automatic override logic
- ✅ **OSC Format Standardization**: Clear separation between `/data/sample` and `/data/batch` modes
- ✅ **Performance Optimizations**: 48x OSC message reduction via intelligent batching
- ✅ **Queue Management**: Overflow strategies with bounded queues
- ✅ **Configuration Validation**: Backward compatibility and hot-reload capabilities
- ✅ **Binary Distribution**: Cross-platform PyInstaller builds
- ✅ **Error Handling**: Graceful degradation throughout
- ✅ **Performance Monitoring**: Real-time metrics and diagnostics with batch efficiency tracking
- ✅ **Thread Safety**: Event-driven architecture with proper synchronization
- ✅ **User Experience**: Clear batch override warnings and status feedback

### Binary Distribution

- **Build Command**: `uv run python build.py`
- **Platforms**: Linux (x64), macOS (Intel/ARM), Windows (x64)
- **Naming**: `openephys-zmq2osc-{platform}-{arch}`
- **Dependencies**: All bundled in single executable
