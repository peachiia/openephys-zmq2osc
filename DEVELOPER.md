# openephys-zmq2osc - Developer Documentation

This document provides detailed technical information for developers who want to understand, modify, extend, or contribute to the OpenEphys ZMQ-to-OSC bridge.

## Architecture Overview

The application follows a **modular, event-driven architecture** with clear separation between backend services and frontend interfaces:

### Core Components

```
src/openephys_zmq2osc/
├── core/
│   ├── services/           # Backend services (ZMQ, OSC, DataManager)
│   ├── events/            # Event bus for inter-service communication  
│   └── models/            # OpenEphys data object definitions
├── interfaces/            # UI layer (CLI, future GUI)
├── config/               # Configuration management
└── main.py              # Application entry point

sandbox/                 # Original prototype files (reference only)
build.py                # Binary build script
test_basic.py           # Basic functionality tests
```

### Design Principles

1. **Separation of Concerns**: Services, UI, and configuration are completely decoupled
2. **Event-Driven Communication**: All components communicate via typed events through EventBus
3. **Thread Safety**: Proper locking and thread-safe data structures throughout
4. **Extensibility**: Abstract interfaces allow easy addition of new UIs or protocols
5. **Configuration-Driven**: Runtime behavior controlled via JSON configuration

## Development Setup

### Prerequisites

- **Python 3.11+**
- **UV Package Manager** - [Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd openephys-zmq2osc

# Setup development environment
uv sync --dev

# Verify installation
uv run python test_basic.py
```

### Development Commands

```bash
# Run application
uv run python -m openephys_zmq2osc.main

# Code formatting
uv run ruff format src/

# Linting
uv run ruff check src/

# Type checking
uv run mypy src/

# Run tests
uv run pytest

# Build binary
uv run python build.py
```

## Core Architecture

### Event-Driven Communication

All components communicate via the `EventBus` using strongly-typed events:

```python
from openephys_zmq2osc.core.events.event_bus import get_event_bus, EventType

# Subscribe to events
event_bus = get_event_bus()
event_bus.subscribe(EventType.DATA_RECEIVED, my_callback)

# Publish events
event_bus.publish_event(
    EventType.ZMQ_CONNECTION_STATUS,
    data={"status": "connected"},
    source="ZMQService"
)
```

**Key Event Types:**
- `ZMQ_CONNECTION_STATUS`, `ZMQ_CONNECTION_ERROR`
- `OSC_CONNECTION_STATUS`, `OSC_CONNECTION_ERROR`
- `DATA_RECEIVED`, `DATA_PROCESSED`, `DATA_SENT`
- `SERVICE_STARTED`, `SERVICE_STOPPED`
- `SHUTDOWN_REQUESTED`

### Threading Model

The application uses a multi-threaded architecture:

- **Main Thread**: UI rendering and event coordination
- **ZMQ Thread**: OpenEphys connection and data reception
- **OSC Thread**: Data processing and OSC transmission
- **Event Thread**: Event bus operations (thread-safe)

All threads coordinate through the EventBus and shut down gracefully.

### Data Flow

1. **ZMQService** connects to OpenEphys, receives neural data frames
2. **DataManager** buffers data in circular arrays per channel
3. When sufficient data is available, **ZMQService** publishes `DATA_PROCESSED` event
4. **OSCService** receives event, queues data, sends via OSC protocol
5. **CLIInterface** updates display in real-time via status events

### Services Detail

#### ZMQService (`core/services/zmq_service.py`)

Handles OpenEphys connection via ZeroMQ:

```python
class ZMQService:
    def __init__(self, ip: str = "localhost", data_port: int = 5556)
    def start() -> None  # Start service in separate thread
    def stop() -> None   # Graceful shutdown
    def get_status() -> dict  # Current connection status
```

**Key Features:**
- Automatic heartbeat management
- Connection retry logic
- Circular data buffering
- Thread-safe event publishing

#### OSCService (`core/services/osc_service.py`)

Manages OSC data transmission:

```python
class OSCService:
    def __init__(self, host: str = "127.0.0.1", port: int = 10000)
    def start() -> None  # Start processing thread
    def stop() -> None   # Graceful shutdown
    def configure(**kwargs) -> None  # Runtime reconfiguration
```

**Key Features:**
- Queue-based data processing
- Two output modes (combined/individual channels)
- Runtime configuration updates
- Connection error handling

#### DataManager (`core/services/data_manager.py`)

Efficient neural data buffering:

```python
class DataManager:
    def init_empty_buffer(self, num_channels: int, num_samples: int) -> None  # Dynamic expansion
    def push_data(self, channel_id: int, data: np.ndarray) -> None
    def pop_data_all_channels(self, num_samples: int) -> list[np.ndarray]
```

**Key Features:**
- Circular buffer implementation
- Per-channel data management
- Thread-safe operations
- Configurable buffer sizes

### Configuration System

Configuration is managed via dataclasses with JSON serialization:

```python
from openephys_zmq2osc.config.settings import get_config

config = get_config()
print(config.zmq.host)  # Access nested configuration
print(config.osc.port)
```

**Configuration Classes:**
- `ZMQConfig` - OpenEphys connection settings
- `OSCConfig` - OSC output configuration
- `UIConfig` - Interface display settings
- `AppConfig` - Application metadata

**Features:**
- JSON schema validation
- Runtime configuration updates
- Environment variable overrides
- Configuration file watching

### Interface System

UI components implement `BaseInterface` for pluggability:

```python
class BaseInterface(ABC):
    @abstractmethod
    def start(self) -> None
    @abstractmethod
    def stop(self) -> None
    @abstractmethod
    def update_zmq_status(self, status_data: dict) -> None
    @abstractmethod
    def update_osc_status(self, status_data: dict) -> None
```

**Current Implementation:**
- `CLIInterface` - Rich-based terminal interface

**Future Possibilities:**
- Web interface via FastAPI
- GUI interface via tkinter/PyQt
- REST API interface
- Headless/daemon mode

## Development Workflows

### Adding a New Service

1. Create service class in `src/openephys_zmq2osc/core/services/`
2. Implement threading and event publishing
3. Add service to main application initialization
4. Add relevant event types to `EventType` enum

Example:
```python
class MIDIService:
    def __init__(self):
        self._event_bus = get_event_bus()
        
    def start(self):
        self._event_bus.subscribe(EventType.DATA_PROCESSED, self._on_data)
        
    def _on_data(self, event):
        # Process neural data and send MIDI
        pass
```

### Adding a New Interface

1. Create interface class in `src/openephys_zmq2osc/interfaces/`
2. Inherit from `BaseInterface`
3. Subscribe to relevant events for UI updates
4. Add interface option to main application

### Extending Configuration

1. Add new dataclass to `src/openephys_zmq2osc/config/settings.py`
2. Include in main `Config` class
3. Update sample configuration generation
4. Add validation logic if needed

### Adding New Event Types

1. Add to `EventType` enum in `src/openephys_zmq2osc/core/events/event_bus.py`
2. Document event data format
3. Add type hints for event data
4. Update relevant services to publish/subscribe

## Testing

### Running Tests

```bash
# Basic functionality test
uv run python test_basic.py

# Full test suite (when available)
uv run pytest

# Test specific component
uv run python -c "from test_basic import test_event_bus; test_event_bus()"
```

### Test Categories

- **Unit Tests**: Individual component testing
- **Integration Tests**: Service interaction testing
- **End-to-End Tests**: Full application workflow testing
- **Performance Tests**: Load and latency testing

### Adding Tests

Create test files following the pattern:
```python
def test_my_feature():
    # Setup
    # Execute
    # Verify
    assert result == expected
```

## Binary Building

### Build Process

The `build.py` script uses PyInstaller to create standalone binaries:

```bash
# Build for current platform
uv run python build.py

# Test built binary
uv run python build.py test

# Create spec file only
uv run python build.py spec
```

### Cross-Platform Building

Build on each target platform:

- **Linux**: Build on Linux (native or container)
- **macOS**: Build on macOS (both Intel and Apple Silicon)
- **Windows**: Build on Windows (native or VM)

### Customizing Builds

Edit `build.py` to modify:
- Hidden imports for new dependencies
- Excluded modules for size optimization
- Platform-specific configurations
- Binary naming conventions

## Performance Considerations

### Data Processing

- **Buffer Sizes**: Balance memory usage vs. latency
- **Circular Buffers**: Efficient memory reuse
- **Threading**: Prevent blocking operations
- **Event Handling**: Minimize event processing time

### Network Performance

- **OSC Message Size**: Combined mode reduces network overhead
- **Buffer Management**: Prevent data loss during network hiccups
- **Connection Pooling**: Reuse connections when possible

### UI Performance

- **Refresh Rate**: Balance responsiveness vs. CPU usage
- **Update Batching**: Group UI updates to reduce overhead
- **Lazy Loading**: Only update visible elements

## Debugging

### Logging Configuration

Enable debug logging in configuration:
```json
{
  "app": {
    "log_level": "DEBUG"
  },
  "ui": {
    "show_debug_info": true
  }
}
```

### Common Debug Patterns

```python
# Event debugging
def debug_event_handler(event):
    print(f"Event: {event.event_type}, Data: {event.data}")

event_bus.subscribe(EventType.DATA_RECEIVED, debug_event_handler)

# Service status debugging
status = zmq_service.get_status()
print(f"ZMQ Status: {status}")

# Configuration debugging
from openephys_zmq2osc.config.settings import get_config
print(get_config().to_dict())
```

### Performance Profiling

```python
# Profile data processing
import cProfile
cProfile.run('zmq_service.run()', 'profile_output')

# Memory profiling
import tracemalloc
tracemalloc.start()
# ... run code ...
current, peak = tracemalloc.get_traced_memory()
```

## Contributing

### Development Process

1. **Fork** the repository
2. **Branch** from main: `git checkout -b feature/my-feature`
3. **Develop** following code style guidelines
4. **Test** thoroughly with `uv run python test_basic.py`
5. **Format** code with `uv run ruff format src/`
6. **Lint** code with `uv run ruff check src/`
7. **Type check** with `uv run mypy src/`
8. **Submit** pull request with clear description

### Code Style

- **Formatting**: Use Ruff formatter
- **Linting**: Follow Ruff recommendations  
- **Type Hints**: Use throughout for better IDE support
- **Docstrings**: Document all public methods
- **Comments**: Explain complex logic, not obvious code

### Commit Guidelines

- Use clear, descriptive commit messages
- Keep commits focused on single changes
- Reference issues where applicable
- Follow conventional commit format

### Documentation

- Update docstrings for new/changed APIs
- Add examples for complex features  
- Update configuration documentation
- Add troubleshooting entries for common issues

## API Reference

### Core Services

**ZMQService**
```python
__init__(ip: str, data_port: int)
start() -> None
stop() -> None
get_status() -> dict
```

**OSCService**  
```python
__init__(host: str, port: int)
start() -> None
stop() -> None
configure(**kwargs) -> None
get_status() -> dict
```

**DataManager**
```python
init_empty_buffer(num_channels: int, num_samples: int) -> None  # Starts with 1, expands dynamically
push_data(channel_id: int, data: np.ndarray) -> None
pop_data_all_channels(num_samples: int) -> list[np.ndarray]
```

### Event System

**EventBus**
```python
subscribe(event_type: EventType, callback: Callable) -> None
unsubscribe(event_type: EventType, callback: Callable) -> None  
publish(event: Event) -> None
publish_event(event_type: EventType, data: Any, source: str) -> None
```

### Configuration

**ConfigManager**
```python
load() -> None
save() -> None
update_zmq_config(**kwargs) -> None
update_osc_config(**kwargs) -> None
```

## Security Considerations

- **Network Security**: OSC and ZMQ are unencrypted protocols
- **Access Control**: No built-in authentication (add proxy if needed)
- **Data Privacy**: Neural data is transmitted in plaintext
- **File Permissions**: Configuration files may contain sensitive info
- **Process Security**: Runs with user privileges by default

## Future Development

### Planned Features

- [ ] Web-based GUI interface
- [ ] MIDI output support  
- [ ] Real-time signal processing filters
- [ ] Multiple OpenEphys source support
- [ ] Data recording capabilities
- [ ] Plugin architecture for custom processors

### Extension Points

- **Protocol Support**: Add TCP, WebSocket, UDP alternatives
- **Data Processing**: Real-time filtering, feature extraction
- **UI Frameworks**: Web, desktop, mobile interfaces
- **Cloud Integration**: Data streaming to cloud services
- **Analytics**: Real-time visualization and analysis

---

This documentation provides the foundation for understanding and extending the OpenEphys ZMQ-to-OSC bridge. For questions or contributions, please refer to the project's GitHub repository.
