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
- Separate config classes for ZMQ, OSC, UI, and app settings

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
3. When sufficient data available, **ZMQService** publishes `DATA_PROCESSED` event
4. **OSCService** receives event, queues data, sends via OSC protocol
5. **CLIInterface** updates display in real-time via status events

### Threading Model

- **Main Thread**: UI rendering and event handling
- **ZMQ Thread**: OpenEphys connection and data reception  
- **OSC Thread**: Queue processing and data transmission
- All threads coordinate via EventBus with proper shutdown handling

### Configuration System

- JSON-based config with dataclass validation
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
