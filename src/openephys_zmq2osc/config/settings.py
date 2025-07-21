import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ZMQConfig:
    host: str = "localhost"
    data_port: int = 5556
    heartbeat_timeout: float = 2.0
    not_responding_timeout: float = 10.0
    app_uuid: str = "1618"
    buffer_size: int = 30000  # 1 second at 30kHz (minimal for real-time)
    # Auto-reinit settings
    data_timeout_seconds: float = 5.0  # Timeout period for data reinit
    auto_reinit_on_timeout: bool = True  # Auto reinit or manual prompt


@dataclass
class OSCConfig:
    host: str = "127.0.0.1"
    port: int = 10000
    base_address: str = "/data"
    send_individual_channels: bool = False
    channel_address_format: str = "/ch{:03d}"


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
class Config:
    zmq: ZMQConfig
    osc: OSCConfig
    ui: UIConfig
    app: AppConfig

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create config from dictionary."""
        return cls(
            zmq=ZMQConfig(**data.get('zmq', {})),
            osc=OSCConfig(**data.get('osc', {})),
            ui=UIConfig(**data.get('ui', {})),
            app=AppConfig(**data.get('app', {}))
        )
    
    def save_to_file(self, filepath: Optional[Path] = None) -> None:
        """Save config to JSON file."""
        if filepath is None:
            filepath = Path(self.app.config_file)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            print(f"Configuration saved to {filepath}")
        except Exception as e:
            print(f"Error saving configuration: {e}")
    
    @classmethod
    def load_from_file(cls, filepath: Optional[Path] = None) -> 'Config':
        """Load config from JSON file."""
        if filepath is None:
            filepath = Path("config.json")
        
        if not filepath.exists():
            print(f"Config file {filepath} not found, using defaults")
            return cls.get_default()
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"Error loading configuration: {e}, using defaults")
            return cls.get_default()
    
    @classmethod
    def get_default(cls) -> 'Config':
        """Get default configuration."""
        return cls(
            zmq=ZMQConfig(),
            osc=OSCConfig(),
            ui=UIConfig(),
            app=AppConfig()
        )


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config.json")
        self._config: Optional[Config] = None
        self._watchers: Dict[str, list] = {}
    
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
        self._notify_watchers('config_loaded')
    
    def save(self) -> None:
        """Save current configuration to file."""
        if self._config:
            self._config.save_to_file(self.config_path)
            self._notify_watchers('config_saved')
    
    def update_zmq_config(self, **kwargs) -> None:
        """Update ZMQ configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config.zmq, key):
                setattr(self.config.zmq, key, value)
        self._notify_watchers('zmq_config_updated')
    
    def update_osc_config(self, **kwargs) -> None:
        """Update OSC configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config.osc, key):
                setattr(self.config.osc, key, value)
        self._notify_watchers('osc_config_updated')
    
    def update_ui_config(self, **kwargs) -> None:
        """Update UI configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config.ui, key):
                setattr(self.config.ui, key, value)
        self._notify_watchers('ui_config_updated')
    
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
    
    def create_sample_config(self) -> None:
        """Create a sample configuration file."""
        config = Config.get_default()
        config.save_to_file(self.config_path)
        print(f"Sample configuration created at {self.config_path}")


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> Config:
    """Get the current configuration."""
    return get_config_manager().config