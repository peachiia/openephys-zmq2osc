import argparse
import signal
import sys
import time
from pathlib import Path

from openephys_zmq2osc.config.settings import ConfigManager, get_config_manager
from openephys_zmq2osc.core.events.event_bus import EventType, get_event_bus
from openephys_zmq2osc.core.services.osc_service import OSCService
from openephys_zmq2osc.core.services.zmq_service import ZMQService
from openephys_zmq2osc.interfaces.cli_interface import CLIInterface


class OpenEphysZMQ2OSC:
    """Main application class."""

    def __init__(self, config_path: Path | None = None):
        # Initialize configuration
        self.config_manager = (
            ConfigManager(config_path) if config_path else get_config_manager()
        )
        self.config = self.config_manager.config

        # Initialize services
        self.zmq_service = ZMQService(
            ip=self.config.zmq.host,
            data_port=self.config.zmq.data_port,
            config=self.config,
        )

        self.osc_service = OSCService(
            host=self.config.osc.host, port=self.config.osc.port, config=self.config
        )

        # Initialize interface
        self.interface = CLIInterface(self.config)

        # Event bus
        self._event_bus = get_event_bus()

        # Shutdown handling
        self._shutdown_requested = False
        self._setup_signal_handlers()

        # Subscribe to shutdown events
        self._event_bus.subscribe(
            EventType.SHUTDOWN_REQUESTED, self._on_shutdown_requested
        )

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            print("\nShutdown requested...")
            self._shutdown_requested = (
                True  # Just set flag, don't call shutdown directly
            )

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _on_shutdown_requested(self, event) -> None:
        """Handle shutdown request event."""
        self._shutdown_requested = True

    def start(self) -> None:
        """Start all services and the interface."""
        print(f"Starting {self.config.app.app_name} v{self.config.app.app_version}")

        try:
            # Start services
            print("Starting ZMQ service...")
            self.zmq_service.start()

            print("Starting OSC service...")
            self.osc_service.start()

            # Start interface
            print("Starting CLI interface...")
            self.interface.start()

            print("All services started successfully")
            print("Press Ctrl+C to stop")

        except Exception as e:
            print(f"Error starting services: {e}")
            self.shutdown()
            return

    def run(self) -> None:
        """Run the main application loop."""
        try:
            while not self._shutdown_requested:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Shutdown all services gracefully."""
        if self._shutdown_requested:
            return  # Already shutting down

        self._shutdown_requested = True
        print("Shutting down services...")

        # Stop interface first (safest - no network operations)
        if self.interface:
            try:
                print("Stopping interface...")
                self.interface.stop()
            except Exception as e:
                print(f"Error stopping interface: {e}")

        # Stop services (may have network cleanup)
        if self.osc_service:
            try:
                print("Stopping OSC service...")
                self.osc_service.stop()
            except Exception as e:
                print(f"Error stopping OSC service: {e}")

        if self.zmq_service:
            try:
                print("Stopping ZMQ service...")
                self.zmq_service.stop()
            except Exception as e:
                print(f"Error stopping ZMQ service: {e}")

        print("Shutdown complete")

    def get_status(self) -> dict:
        """Get overall application status."""
        return {
            "app_name": self.config.app.app_name,
            "app_version": self.config.app.app_version,
            "running": not self._shutdown_requested,
            "zmq_service": self.zmq_service.get_status() if self.zmq_service else None,
            "osc_service": self.osc_service.get_status() if self.osc_service else None,
            "interface_running": self.interface.is_running if self.interface else False,
        }


def create_config_file(config_path: Path, minimal: bool = True) -> None:
    """Create a sample configuration file."""
    config_manager = ConfigManager(config_path)
    config_manager.create_sample_config(minimal=minimal)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OpenEphys ZMQ to OSC Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  openephys-zmq2osc                           # Run with default config
  openephys-zmq2osc --config my_config.json  # Run with custom config
  openephys-zmq2osc --create-config          # Create minimal config file (default)
  openephys-zmq2osc --create-config-dev      # Create full config file with all options
  openephys-zmq2osc --zmq-host 192.168.1.100 # Override ZMQ host
  openephys-zmq2osc --osc-port 8000          # Override OSC port
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Configuration file path (default: config.json)",
    )

    parser.add_argument(
        "--create-config",
        action="store_true",
        help="Create a minimal sample configuration file and exit",
    )
    parser.add_argument(
        "--create-config-dev",
        action="store_true",
        help="Create a full developer configuration file with all options and exit",
    )

    parser.add_argument("--zmq-host", help="Override ZMQ host address")

    parser.add_argument("--zmq-port", type=int, help="Override ZMQ data port")

    parser.add_argument("--osc-host", help="Override OSC host address")

    parser.add_argument("--osc-port", type=int, help="Override OSC port")

    parser.add_argument("--version", "-v", action="version", version="%(prog)s 0.1.0")

    args = parser.parse_args()

    # Handle config creation
    if args.create_config:
        config_path = args.config or Path("config.json")
        create_config_file(config_path, minimal=True)
        return

    if args.create_config_dev:
        config_path = args.config or Path("config-dev.json")
        create_config_file(config_path, minimal=False)
        return

    try:
        # Initialize application
        app = OpenEphysZMQ2OSC(args.config)

        # Apply command line overrides
        if args.zmq_host:
            app.config_manager.update_zmq_config(host=args.zmq_host)
        if args.zmq_port:
            app.config_manager.update_zmq_config(data_port=args.zmq_port)
        if args.osc_host:
            app.config_manager.update_osc_config(host=args.osc_host)
        if args.osc_port:
            app.config_manager.update_osc_config(port=args.osc_port)

        # Start and run application
        app.start()
        app.run()

    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
