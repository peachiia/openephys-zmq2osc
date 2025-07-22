import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ZMQConfig:
    host: str = "localhost"
    data_port: int = 5556
    heartbeat_timeout: float = 2.0
    not_responding_timeout: float = 10.0
    app_uuid: str = "1618"
    buffer_size: int = 30000  # 1 second at 30kHz (minimal for real-time)
    # Auto-reinit settings
    data_timeout_seconds: float = 2.0  # Timeout period for data reinit
    auto_reinit_on_timeout: bool = True  # Auto reinit or manual prompt


@dataclass
class ProcessingConfig:
    """Unified processing configuration for downsampling and batching."""

    downsampling_factor: int = 30  # 1 = no downsampling, 30 = 30:1 reduction
    downsampling_method: str = "average"  # "average", "decimate"
    batch_size: int = 1  # Number of samples per OSC message (1 = no batching)
    batch_timeout_ms: float = 1000.0  # Send partial batches after timeout


@dataclass
class OSCConfig:
    host: str = "127.0.0.1"
    port: int = 10000
    base_address: str = "/data"
    send_individual_channels: bool = False
    channel_address_format: str = "/ch{:03d}"

    # Unified processing configuration
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)


@dataclass
class UIConfig:
    refresh_rate: int = 10  # Hz
    theme: str = "default"
    show_debug_info: bool = False


@dataclass
class AppConfig:
    app_name: str = "OpenEphys - ZMQ to OSC"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    config_file: str = "config.json"


@dataclass
class PerformanceConfig:
    """Performance optimization settings for high-throughput scenarios."""

    # OSC batching configuration (batch_size moved to ProcessingConfig)
    osc_queue_max_size: int = 100  # Maximum queue size before overflow handling
    osc_queue_overflow_strategy: str = (
        "drop_oldest"  # "drop_oldest", "drop_newest", "block"
    )

    # UI and monitoring configuration
    ui_update_interval_ms: int = 100  # UI update interval during high-throughput
    metrics_collection_interval_ms: int = 250  # How often to collect detailed metrics

    # Performance mode presets
    mode: str = "balanced"  # "low_latency", "balanced", "high_throughput"

    # Advanced settings
    enable_batching: bool = False  # Master switch for batching optimizations
    adaptive_batching: bool = False  # Automatically adjust batch size based on load


@dataclass
class Config:
    zmq: ZMQConfig
    osc: OSCConfig
    ui: UIConfig
    app: AppConfig
    performance: PerformanceConfig

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create config from dictionary, handling both full and minimal formats."""
        # Handle ZMQ config
        zmq_data = data.get("zmq", {})

        # Handle performance data that might be split between performance section and ZMQ section
        performance_data = data.get("performance", {})

        # Map minimal config ZMQ timeout fields to full config fields
        if "zmq_not_responding_timeout" in performance_data:
            zmq_data["not_responding_timeout"] = performance_data["zmq_not_responding_timeout"]
        if "zmq_data_timeout_seconds" in performance_data:
            zmq_data["data_timeout_seconds"] = performance_data["zmq_data_timeout_seconds"]
        if "zmq_auto_reinit_on_timeout" in performance_data:
            zmq_data["auto_reinit_on_timeout"] = performance_data["zmq_auto_reinit_on_timeout"]

        # Handle OSC config with nested processing config
        osc_data = data.get("osc", {})
        if "processing" in osc_data:
            processing_data = osc_data["processing"].copy()
            # Move enable_batching from processing to performance if present
            if "enable_batching" in processing_data:
                performance_data["enable_batching"] = processing_data.pop("enable_batching")
            processing_config = ProcessingConfig(**processing_data)
        else:
            processing_config = ProcessingConfig()

        # Create OSC config with processing config
        osc_config = OSCConfig(
            **{k: v for k, v in osc_data.items() if k != "processing"}
        )
        osc_config.processing = processing_config

        # Clean up performance data by removing ZMQ-specific fields
        clean_performance_data = {
            k: v for k, v in performance_data.items()
            if not k.startswith("zmq_")
        }

        return cls(
            zmq=ZMQConfig(**zmq_data),
            osc=osc_config,
            ui=UIConfig(**data.get("ui", {})),
            app=AppConfig(**data.get("app", {})),
            performance=PerformanceConfig(**clean_performance_data),
        )

    def save_to_file(self, filepath: Path | None = None) -> None:
        """Save config to JSON file."""
        if filepath is None:
            filepath = Path(self.app.config_file)

        try:
            with open(filepath, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            print(f"Configuration saved to {filepath}")
        except Exception as e:
            print(f"Error saving configuration: {e}")

    @classmethod
    def load_from_file(cls, filepath: Path | None = None) -> "Config":
        """Load config from JSON file."""
        if filepath is None:
            filepath = Path("config.json")

        if not filepath.exists():
            print(f"Config file {filepath} not found, using defaults")
            return cls.get_default()

        try:
            with open(filepath) as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"Error loading configuration: {e}, using defaults")
            return cls.get_default()

    @classmethod
    def get_default(cls) -> "Config":
        """Get default configuration."""
        return cls(
            zmq=ZMQConfig(),
            osc=OSCConfig(),
            ui=UIConfig(),
            app=AppConfig(),
            performance=PerformanceConfig(),
        )


class ConfigManager:
    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or Path("config.json")
        self._config: Config | None = None
        self._watchers: dict[str, list] = {}

    @property
    def config(self) -> Config:
        """Get current configuration."""
        if self._config is None:
            self.load()
        assert self._config is not None, "Config should be loaded"
        return self._config

    def load(self) -> None:
        """Load configuration from file."""
        self._config = Config.load_from_file(self.config_path)
        self._notify_watchers("config_loaded")

    def save(self) -> None:
        """Save current configuration to file."""
        if self._config:
            self._config.save_to_file(self.config_path)
            self._notify_watchers("config_saved")

    def update_zmq_config(self, **kwargs) -> None:
        """Update ZMQ configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config.zmq, key):
                setattr(self.config.zmq, key, value)
        self._notify_watchers("zmq_config_updated")

    def update_osc_config(self, **kwargs) -> None:
        """Update OSC configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config.osc, key):
                setattr(self.config.osc, key, value)
        self._notify_watchers("osc_config_updated")

    def update_ui_config(self, **kwargs) -> None:
        """Update UI configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config.ui, key):
                setattr(self.config.ui, key, value)
        self._notify_watchers("ui_config_updated")

    def add_watcher(self, event: str, callback) -> None:
        """Add a callback to be notified of configuration changes."""
        if event not in self._watchers:
            self._watchers[event] = []
        self._watchers[event].append(callback)

    def remove_watcher(self, event: str, callback) -> None:
        """Remove a configuration change callback."""
        if event in self._watchers and callback in self._watchers[event]:
            self._watchers[event].remove(callback)

    def _notify_watchers(self, event: str) -> None:
        """Notify all watchers of a configuration event."""
        if event in self._watchers:
            for callback in self._watchers[event]:
                try:
                    callback(self.config)
                except Exception as e:
                    print(f"Error in config watcher callback: {e}")

    def create_sample_config(self, minimal: bool = True) -> None:
        """Create a sample configuration file."""
        config = Config.get_default()
        if minimal:
            self._save_minimal_config(config, self.config_path)
            print(f"Minimal configuration created at {self.config_path}")
        else:
            config.save_to_file(self.config_path)
            print(f"Full configuration created at {self.config_path}")

    def _save_minimal_config(self, config: Config, filepath: Path) -> None:
        """Save a minimal configuration format."""
        minimal_data = {
            "zmq": {
                "host": config.zmq.host,
                "data_port": config.zmq.data_port,
                "app_uuid": config.zmq.app_uuid
            },
            "osc": {
                "host": config.osc.host,
                "port": config.osc.port,
                "base_address": config.osc.base_address,
                "processing": {
                    "downsampling_factor": config.osc.processing.downsampling_factor,
                    "downsampling_method": config.osc.processing.downsampling_method,
                    "enable_batching": config.performance.enable_batching,
                    "batch_size": config.osc.processing.batch_size
                }
            },
            "performance": {
                "zmq_not_responding_timeout": config.zmq.not_responding_timeout,
                "zmq_data_timeout_seconds": config.zmq.data_timeout_seconds,
                "zmq_auto_reinit_on_timeout": config.zmq.auto_reinit_on_timeout,
                "osc_queue_max_size": config.performance.osc_queue_max_size,
                "osc_queue_overflow_strategy": config.performance.osc_queue_overflow_strategy
            }
        }

        try:
            with open(filepath, "w") as f:
                json.dump(minimal_data, f, indent=2)
        except Exception as e:
            print(f"Error saving minimal configuration: {e}")


# Global configuration manager instance
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> Config:
    """Get the current configuration."""
    return get_config_manager().config
