import time
import threading
import select
import sys
import termios
import tty
from datetime import datetime
from typing import Dict, Any, Optional
from rich.console import Console
from rich.layout import Layout
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.rule import Rule

from .base_interface import BaseInterface
from ..config.settings import Config
from ..core.events.event_bus import get_event_bus, EventType, Event


class CLIInterface(BaseInterface):
    """Rich-based command-line interface."""
    
    custom_theme = Theme({
        "val_success": "bold green",
        "val_error": "bold red",
        "val_warning": "bold yellow",
        "default": "orange1",
        "grid_rule": "dim",
        "connected": "bold green",
        "connecting": "bold yellow",
        "disconnected": "bold red",
        "not_responding": "bold red",
        "online": "bold bright_green",
    })
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.console = Console(theme=self.custom_theme)
        self.layout: Optional[Layout] = None
        self.live_display: Optional[Live] = None
        self._display_thread: Optional[threading.Thread] = None
        self._event_bus = get_event_bus()
        
        # Status data
        self._zmq_status = {
            "connection_status": "not_connected",
            "ip": config.zmq.host,
            "data_port": config.zmq.data_port,
            "heartbeat_port": config.zmq.data_port + 1,
            "app_name": f"{config.app.app_name}",
            "uuid": config.zmq.app_uuid,
            "message_num": 0
        }
        
        self._osc_status = {
            "running": False,
            "connected": False,
            "host": config.osc.host,
            "port": config.osc.port,
            "messages_sent": 0,
            "queue_size": 0,
            "avg_delay_ms": 0.0,
            "calculated_sample_rate": 30000.0,
            "mean_sample_rate": 30000.0,
            "data_flow_active": False
        }
        
        self._data_stats = {
            "channels_received": 0,
            "samples_processed": 0,
            "last_update": None
        }
        
        self._channel_info = {
            "discovery_mode": True,
            "total_channels": 0,
            "discovered_channels": [],
            "channel_list": []
        }
        
        self._error_messages = []
        self._info_messages = []
        
        # Timeout status
        self._timeout_status = {
            "timeout_triggered": False,
            "manual_reinit_available": False,
            "timeout_seconds": config.zmq.data_timeout_seconds,
            "auto_reinit_enabled": config.zmq.auto_reinit_on_timeout,
            "time_until_timeout": 0.0,
            "data_receiving": False,  # Start as false until data comes in
            "last_data_time": 0.0,
            "chunk_delay_ms": 0.0,  # ZMQ chunk delay tracking
            "samples_per_chunk": 0  # Samples per chunk
        }
        
        # Keyboard handling
        self._keyboard_thread: Optional[threading.Thread] = None
        self._original_termios = None
        
        self._setup_event_subscriptions()
    
    def _setup_event_subscriptions(self) -> None:
        """Subscribe to relevant events."""
        self._event_bus.subscribe(EventType.ZMQ_CONNECTION_STATUS, self._on_zmq_status_update)
        self._event_bus.subscribe(EventType.ZMQ_CONNECTION_ERROR, self._on_zmq_error)
        self._event_bus.subscribe(EventType.OSC_CONNECTION_STATUS, self._on_osc_status_update)
        self._event_bus.subscribe(EventType.OSC_CONNECTION_ERROR, self._on_osc_error)
        self._event_bus.subscribe(EventType.DATA_RECEIVED, self._on_data_received)
        self._event_bus.subscribe(EventType.DATA_SENT, self._on_data_sent)
        self._event_bus.subscribe(EventType.STATUS_UPDATE, self._on_status_update)
    
    def start(self) -> None:
        """Start the CLI interface."""
        if self._running:
            return
            
        self._running = True
        self.layout = self._init_layout()
        self._update_layout()
        
        # Setup terminal for raw input
        self._setup_terminal()
        
        self.live_display = Live(
            self.layout, 
            console=self.console, 
            auto_refresh=True, 
            screen=True, 
            refresh_per_second=self.config.ui.refresh_rate
        )
        
        self._display_thread = threading.Thread(target=self._run_display, daemon=True)
        self._display_thread.start()
        
        # Start keyboard handling
        self._keyboard_thread = threading.Thread(target=self._handle_keyboard_input, daemon=True)
        self._keyboard_thread.start()
    
    def stop(self) -> None:
        """Stop the CLI interface."""
        self._running = False
        
        # Unsubscribe from events
        self._event_bus.unsubscribe(EventType.ZMQ_CONNECTION_STATUS, self._on_zmq_status_update)
        self._event_bus.unsubscribe(EventType.ZMQ_CONNECTION_ERROR, self._on_zmq_error)
        self._event_bus.unsubscribe(EventType.OSC_CONNECTION_STATUS, self._on_osc_status_update)
        self._event_bus.unsubscribe(EventType.OSC_CONNECTION_ERROR, self._on_osc_error)
        self._event_bus.unsubscribe(EventType.DATA_RECEIVED, self._on_data_received)
        self._event_bus.unsubscribe(EventType.DATA_SENT, self._on_data_sent)
        self._event_bus.unsubscribe(EventType.STATUS_UPDATE, self._on_status_update)
        
        if self.live_display:
            self.live_display.stop()
            self.live_display = None
        
        if self._display_thread and self._display_thread.is_alive():
            self._display_thread.join(timeout=1.0)
            
        if self._keyboard_thread and self._keyboard_thread.is_alive():
            self._keyboard_thread.join(timeout=1.0)
            
        # Restore terminal settings
        self._restore_terminal()
    
    def _run_display(self) -> None:
        """Run the live display."""
        try:
            with self.live_display:
                last_update = time.time()
                while self._running:
                    current_time = time.time()
                    # Update layout every second to refresh clock
                    if current_time - last_update >= 1.0:
                        self._update_layout()
                        last_update = current_time
                    time.sleep(0.1)  # Control update frequency
        except KeyboardInterrupt:
            self._running = False
    
    def _init_layout(self) -> Layout:
        """Initialize the Rich layout."""
        layout = Layout(name="root")
        
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3)
        )
        
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        
        return layout
    
    def _update_layout(self) -> None:
        """Update all layout components."""
        if not self.layout:
            return
        
        # Check for data timeout before updating layout
        self._check_data_timeout()
            
        self.layout["header"].update(self._create_header_panel())
        self.layout["left"].update(self._create_zmq_panel())
        self.layout["right"].update(self._create_osc_panel())
        self.layout["footer"].update(self._create_footer_panel())
    
    def _create_header_panel(self) -> Panel:
        """Create the header panel."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right")
        
        current_time = datetime.now().ctime().replace(":", "[blink]:[/]")
        app_title = f"[b]{self.config.app.app_name}[/b] [dim]v{self.config.app.app_version}[/dim]"
        
        grid.add_row(app_title, current_time)
        
        return Panel(grid, style="default")
    
    def _create_zmq_panel(self) -> Panel:
        """Create the ZMQ status panel."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="left", ratio=2)
        
        # Connection details
        grid.add_row("App Name", self._zmq_status["app_name"])
        grid.add_row("UUID", self._zmq_status["uuid"])
        grid.add_row("Address", self._zmq_status["ip"])
        grid.add_row("Data Port", str(self._zmq_status["data_port"]))
        
        grid.add_row(Rule(style="grid_rule"), Rule(style="grid_rule"))
        
        # Derived info
        identity = f"{self._zmq_status['app_name']}-{self._zmq_status['uuid']}"
        heartbeat_port = f"{self._zmq_status['heartbeat_port']} (DP+1)"
        grid.add_row("[dim][i]Identity[/i][/dim]", f"[dim][i]{identity}[/i][/dim]")
        grid.add_row("[dim][i]HB Port[/i][/dim]", f"[dim][i]{heartbeat_port}[/i][/dim]")
        
        grid.add_row("", "")
        
        # Status
        status = self._zmq_status["connection_status"].replace("_", " ").title()
        status_style = self._get_status_style(self._zmq_status["connection_status"])
        grid.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
        
        grid.add_row(Rule(style="default"), Rule(style="default"))
        
        # Channel discovery info
        if self._channel_info["discovery_mode"]:
            discovery_info = f"Discovering... ({len(self._channel_info['discovered_channels'])} found)"
            grid.add_row("Channels", f"[val_warning]{discovery_info}[/val_warning]")
        elif self._channel_info["total_channels"] > 0:
            channels_info = f"{self._channel_info['total_channels']} channels ready"
            grid.add_row("Channels", f"[val_success]{channels_info}[/val_success]")
            
            # Show chunk delay information
            samples_per_chunk = self._timeout_status["samples_per_chunk"]
            chunk_delay = self._timeout_status["chunk_delay_ms"]
            if samples_per_chunk > 0:
                chunk_info = f"{samples_per_chunk} s/p ({chunk_delay:.1f} ms)"
                grid.add_row("", f"[dim]{chunk_info}[/dim]")
            
            # Show channel list with OSC mapping (first few channels)
            if self._channel_info["channel_list"]:
                channel_mappings = []
                for ch in self._channel_info["channel_list"][:4]:  # Show first 4 for OSC mapping
                    if ch.get("discovered", False):
                        ch_id = ch.get("id", 0)
                        ch_label = ch.get("label", f"CH{ch_id}")
                        osc_addr = f"/ch{ch_id:03d}"
                        mapping = f"{ch_label}→{osc_addr}"
                        channel_mappings.append(f"[val_success]{mapping}[/val_success]")
                    else:
                        ch_id = ch.get("id", 0) 
                        ch_label = ch.get("label", f"CH{ch_id}")
                        mapping = f"{ch_label}→/ch{ch_id:03d}"
                        channel_mappings.append(f"[dim]{mapping}[/dim]")
                
                more_text = f" +{len(self._channel_info['channel_list'])-4}" if len(self._channel_info["channel_list"]) > 4 else ""
                grid.add_row("OSC Mapping", f"[dim]{', '.join(channel_mappings)}{more_text}[/dim]")
        else:
            grid.add_row("Channels", "Waiting for data...")
            grid.add_row("", "[dim]Chunk 0(0.0 ms)[/dim]")
        
        # Data timeout and auto-reinit status
        grid.add_row("", "")
        
        # Show data receiving status and timeout info
        if self._timeout_status["data_receiving"]:
            timeout_seconds = self._timeout_status['timeout_seconds']
            grid.add_row("Data Status", f"[val_success]Receiving ({timeout_seconds:.1f}s)[/val_success]")
        else:
            if self._timeout_status["timeout_triggered"]:
                grid.add_row("Data Status", "[val_error]Timeout reached[/val_error]")
            else:
                grid.add_row("Data Status", "[val_warning]No data[/val_warning]")
        
        # Show auto-reinit setting and status
        if self._timeout_status["auto_reinit_enabled"]:
            auto_status = "[val_success]ON[/val_success]"
        else:
            auto_status = "[val_warning]Manual only[/val_warning] (Ctrl+F)"
        grid.add_row("Auto-reinit", auto_status)
        
        # Error messages
        if self._error_messages:
            grid.add_row("", "")
            for error in self._error_messages[-2:]:  # Show last 2 errors
                grid.add_row("[val_error]Error[/val_error]", f"[dim]{error}[/dim]")
        
        return Panel(grid, title="ZMQ (OpenEphys Server)", border_style="default")
    
    def _create_osc_panel(self) -> Panel:
        """Create the OSC status panel."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="left", ratio=2)
        
        # Connection details
        grid.add_row("Address", self._osc_status["host"])
        grid.add_row("Port", str(self._osc_status["port"]))
        
        grid.add_row("", Rule(style="grid_rule"))
        
        # Configuration - show dynamic channel count
        if self._channel_info["total_channels"] > 0:
            channels_text = str(self._channel_info["total_channels"])
            if self._channel_info["discovery_mode"]:
                channels_text += " (discovering...)"
        else:
            channels_text = "Auto-detect"
        grid.add_row("Channels", channels_text)
        
        # Dynamic sampling rate display with mean rate on separate lines
        data_active = self._osc_status.get("data_flow_active", False)
        current_rate = self._osc_status.get("calculated_sample_rate", 30000.0)
        mean_rate = self._osc_status.get("mean_sample_rate", 30000.0)
        
        if data_active and current_rate > 0:
            # Show current rate on first line
            current_text = f"{current_rate:.1f}"
            grid.add_row("Sample Rate", current_text)
            # Show mean rate on second line if significantly different
            if abs(current_rate - mean_rate) > 100:
                mean_text = f"{mean_rate:.1f} (mean)"
                grid.add_row("", f"[dim]{mean_text}[/dim]")
        elif not data_active:
            # Show zero with indicator when no data
            grid.add_row("Sample Rate", "[dim]0 *no data[/dim]")
            grid.add_row("", "[dim]0 (mean)[/dim]")
        else:
            grid.add_row("Sample Rate", "30000 (default)")
            grid.add_row("", "[dim]30000 (mean)[/dim]")
        
        grid.add_row(Rule(style="grid_rule"), Rule(style="grid_rule"))
        
        # Status
        if self._osc_status["running"] and self._osc_status["connected"]:
            status = "Online"
            status_style = "online"
        elif self._osc_status["running"]:
            status = "Starting"
            status_style = "connecting"
        else:
            status = "Disconnected"
            status_style = "disconnected"
        
        grid.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
        
        grid.add_row(Rule(style="default"), Rule(style="default"))
        
        # Statistics
        if self._osc_status["messages_sent"] > 0:
            # Messages and queue info
            stats = f"Sent: {self._osc_status['messages_sent']} | Queue: {self._osc_status['queue_size']}"
            grid.add_row("Messages", stats)
            
            # Delay information
            delay_ms = self._osc_status.get("avg_delay_ms", 0.0)
            data_active = self._osc_status.get("data_flow_active", False)
            
            if data_active and delay_ms > 0:
                if delay_ms < 20.0:
                    delay_text = f"{delay_ms:.2f} ms"
                    delay_style = "val_success"  # Green for low delay
                elif delay_ms < 300.0:
                    delay_text = f"{delay_ms:.1f} ms"
                    delay_style = "val_warning"  # Yellow for moderate delay
                else:
                    delay_text = f"{delay_ms:.1f} ms"
                    delay_style = "val_error"    # Red for high delay
                
                grid.add_row("OSC Delay", f"[{delay_style}]{delay_text}[/{delay_style}]")
            elif not data_active:
                grid.add_row("OSC Delay", "[dim]0 ms *no data[/dim]")
            else:
                grid.add_row("OSC Delay", "[dim]Calculating...[/dim]")
        else:
            grid.add_row("No Data Sent", "")
        
        return Panel(grid, title="OSC", border_style="default")
    
    def _create_footer_panel(self) -> Panel:
        """Create the footer panel."""
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        # Show recent info messages
        info_text = ""
        if self._info_messages:
            info_text = self._info_messages[-1]  # Show most recent info
        
        # Left side - controls
        left_controls = "[dim]Press Ctrl+C to quit | Ctrl+F to reinit[/dim]"
        
        grid.add_row(
            left_controls,
            info_text,
            f"[dim]Refresh: {self.config.ui.refresh_rate}Hz[/dim]"
        )
        
        return Panel(grid, style="dim")
    
    def _get_status_style(self, status: str) -> str:
        """Get the appropriate style for a connection status."""
        status_styles = {
            "not_connected": "disconnected",
            "disconnected": "disconnected", 
            "reconnecting": "connecting",
            "connecting": "connecting",
            "connected": "connected",
            "online": "online",
            "not_responding": "not_responding"
        }
        return status_styles.get(status, "default")
    
    def _on_zmq_status_update(self, event: Event) -> None:
        """Handle ZMQ status update events."""
        if event.data:
            self._zmq_status.update(event.data)
            self._update_layout()
    
    def _on_zmq_error(self, event: Event) -> None:
        """Handle ZMQ error events."""
        if event.data and "error" in event.data:
            error_msg = event.data["error"]
            self.show_error(error_msg, "ZMQ")
    
    def _on_osc_status_update(self, event: Event) -> None:
        """Handle OSC status update events."""
        if event.data:
            self._osc_status.update(event.data)
            self._update_layout()
    
    def _on_osc_error(self, event: Event) -> None:
        """Handle OSC error events."""
        if event.data and "error" in event.data:
            error_msg = event.data["error"]
            self.show_error(error_msg, "OSC")
    
    def _on_data_received(self, event: Event) -> None:
        """Handle data received events."""
        if event.data:
            self._data_stats["channels_received"] = event.data.get("channel_num", 0)
            self._data_stats["last_update"] = datetime.now()
            
            # Update data receiving status and timestamp
            self._timeout_status["data_receiving"] = True
            self._timeout_status["timeout_triggered"] = False
            self._timeout_status["last_data_time"] = time.time()
            
            # Update chunk delay and samples per chunk if available
            if "chunk_delay_ms" in event.data:
                self._timeout_status["chunk_delay_ms"] = event.data["chunk_delay_ms"]
            if "num_samples" in event.data:
                self._timeout_status["samples_per_chunk"] = event.data["num_samples"]
            
            # Update discovery status if in discovery mode
            discovery_status = event.data.get("discovery_status", {})
            if discovery_status.get("discovery_mode", False):
                self._channel_info.update({
                    "discovery_mode": True,
                    "discovered_channels": discovery_status.get("discovered_channels", []),
                    "total_channels": len(discovery_status.get("discovered_channels", []))
                })
            
            self._update_layout()
    
    def _on_data_sent(self, event: Event) -> None:
        """Handle data sent events."""
        if event.data:
            self._osc_status["messages_sent"] = event.data.get("messages_sent", 0)
            self._osc_status["queue_size"] = event.data.get("queue_size", 0)
            self._osc_status["avg_delay_ms"] = event.data.get("avg_delay_ms", 0.0)
            self._osc_status["calculated_sample_rate"] = event.data.get("calculated_sample_rate", 30000.0)
            self._osc_status["mean_sample_rate"] = event.data.get("mean_sample_rate", 30000.0)
            self._osc_status["data_flow_active"] = event.data.get("data_flow_active", False)
            self._data_stats["samples_processed"] = event.data.get("num_samples", 0)
            self._update_layout()

    def _on_status_update(self, event: Event) -> None:
        """Handle status update events."""
        if not event.data:
            return
            
        # Prevent infinite recursion - don't process our own events
        if event.source == "CLIInterface":
            return
            
        event_type = event.data.get("type")
        
        if event_type == "channel_discovery_complete":
            # Channel discovery completed
            self._channel_info.update({
                "discovery_mode": False,
                "total_channels": event.data.get("total_channels", 0),
                "discovered_channels": event.data.get("discovered_channels", []),
                "channel_list": event.data.get("channel_info", [])
            })
            
            # Show completion message
            self.show_message(f"Channel discovery complete! Found {self._channel_info['total_channels']} channels.", "info")
            
        elif event_type == "data_timeout_warning":
            # Data timeout detected - show warning and enable manual reinit
            timeout_status = event.data.get("timeout_status", {})
            self._timeout_status.update(timeout_status)
            self._timeout_status["manual_reinit_available"] = True
            self._timeout_status["data_receiving"] = False
            self._timeout_status["timeout_triggered"] = True
            
            timeout_sec = timeout_status.get("timeout_seconds", 5)
            self.show_message(f"Data timeout ({timeout_sec}s) - Press Ctrl+F to reinit channels", "warning")
            
        elif event_type == "auto_reinit_completed":
            # Auto reinit completed
            prev_channels = event.data.get("previous_channels", 0)
            timeout_sec = event.data.get("timeout_seconds", 5)
            self._timeout_status["manual_reinit_available"] = False
            self._timeout_status["timeout_triggered"] = False
            self._timeout_status["chunk_delay_ms"] = 0.0  # Reset chunk delay
            self._timeout_status["samples_per_chunk"] = 0  # Reset samples per chunk
            
            self.show_message(f"Auto reinit: {prev_channels} → 1 channel (timeout: {timeout_sec}s)", "info")
            
        elif event_type == "manual_reinit_completed":
            # Manual reinit completed
            prev_channels = event.data.get("previous_channels", 0)
            self._timeout_status["manual_reinit_available"] = False
            self._timeout_status["timeout_triggered"] = False
            self._timeout_status["chunk_delay_ms"] = 0.0  # Reset chunk delay
            self._timeout_status["samples_per_chunk"] = 0  # Reset samples per chunk
            
            self.show_message(f"Manual reinit: {prev_channels} → 1 channel", "info")
            
        elif event_type == "manual_reinit_request":
            # Manual reinit was requested - forward to ZMQ service
            self._event_bus.publish_event(
                EventType.STATUS_UPDATE,
                data={
                    "type": "execute_manual_reinit"
                },
                source="CLIInterface"
            )
            
        self._update_layout()
    
    def update_zmq_status(self, status_data: Dict[str, Any]) -> None:
        """Update ZMQ status display."""
        self._zmq_status.update(status_data)
        self._update_layout()
    
    def update_osc_status(self, status_data: Dict[str, Any]) -> None:
        """Update OSC status display."""
        self._osc_status.update(status_data)
        self._update_layout()
    
    def update_data_stats(self, stats_data: Dict[str, Any]) -> None:
        """Update data processing statistics."""
        self._data_stats.update(stats_data)
        self._update_layout()
    
    def show_error(self, error_message: str, source: str = None) -> None:
        """Display an error message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_error = f"[{timestamp}] {error_message}"
        if source:
            formatted_error = f"[{timestamp}] {source}: {error_message}"
        
        self._error_messages.append(formatted_error)
        # Keep only last 10 errors
        if len(self._error_messages) > 10:
            self._error_messages.pop(0)
        
        self._update_layout()
    
    def show_message(self, message: str, level: str = "info") -> None:
        """Display a general message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        if level == "info":
            self._info_messages.append(formatted_message)
            # Keep only last 5 info messages
            if len(self._info_messages) > 5:
                self._info_messages.pop(0)
        
        self._update_layout()
    
    def clear_screen(self) -> None:
        """Clear the console screen."""
        self.console.clear()
    
    def _setup_terminal(self) -> None:
        """Setup terminal for raw keyboard input."""
        if hasattr(sys.stdin, 'fileno') and sys.stdin.isatty():
            try:
                self._original_termios = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
            except (termios.error, OSError):
                self._original_termios = None
    
    def _restore_terminal(self) -> None:
        """Restore original terminal settings."""
        if self._original_termios and hasattr(sys.stdin, 'fileno'):
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._original_termios)
            except (termios.error, OSError):
                pass
    
    def _handle_keyboard_input(self) -> None:
        """Handle keyboard input in a separate thread."""
        while self._running:
            if hasattr(sys.stdin, 'fileno') and sys.stdin.isatty():
                try:
                    # Check if input is available without blocking
                    ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if ready:
                        key = sys.stdin.read(1)
                        if key == '\x06':  # Ctrl+F
                            self._handle_manual_reinit_request()
                        elif key == '\x03':  # Ctrl+C
                            self._running = False
                            break
                except (OSError, IOError):
                    time.sleep(0.1)
            else:
                time.sleep(0.1)
    
    def _handle_manual_reinit_request(self) -> None:
        """Handle manual reinit request via Ctrl+F."""
        # Allow manual reinit at any time
        self._event_bus.publish_event(
            EventType.STATUS_UPDATE,
            data={
                "type": "manual_reinit_request",
                "source": "cli_interface"
            },
            source="CLIInterface"
        )
        self.show_message("Manual reinit requested...", "info")
    
    def _check_data_timeout(self) -> None:
        """Check if data has timed out and update status accordingly."""
        if self._timeout_status["last_data_time"] == 0.0:
            # No data received yet
            return
        
        current_time = time.time()
        time_since_data = current_time - self._timeout_status["last_data_time"]
        timeout_seconds = self._timeout_status["timeout_seconds"]
        
        if time_since_data > timeout_seconds:
            # Data has timed out
            if self._timeout_status["data_receiving"]:
                self._timeout_status["data_receiving"] = False
                # Don't set timeout_triggered here as that's handled by ZMQ service events
        else:
            # Data is still coming
            if not self._timeout_status["data_receiving"] and not self._timeout_status["timeout_triggered"]:
                self._timeout_status["data_receiving"] = True