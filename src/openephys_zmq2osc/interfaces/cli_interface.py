import time
import threading
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
            "queue_size": 0
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
        
        self.live_display = Live(
            self.layout, 
            console=self.console, 
            auto_refresh=True, 
            screen=True, 
            refresh_per_second=self.config.ui.refresh_rate
        )
        
        self._display_thread = threading.Thread(target=self._run_display, daemon=True)
        self._display_thread.start()
    
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
    
    def _run_display(self) -> None:
        """Run the live display."""
        try:
            with self.live_display:
                while self._running:
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
            
            # Show channel list (first few channels)
            if self._channel_info["channel_list"]:
                channel_names = []
                for ch in self._channel_info["channel_list"][:6]:  # Show first 6
                    if ch.get("discovered", False):
                        channel_names.append(f"[val_success]{ch['label']}[/val_success]")
                    else:
                        channel_names.append(f"[dim]{ch['label']}[/dim]")
                
                more_text = f" +{len(self._channel_info['channel_list'])-6}" if len(self._channel_info["channel_list"]) > 6 else ""
                grid.add_row("", f"[dim]{', '.join(channel_names)}{more_text}[/dim]")
        else:
            grid.add_row("Channels", "Waiting for data...")
        
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
        grid.add_row("Sample Rate", "30000 Hz")  # Default OpenEphys rate
        
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
            stats = f"Sent: {self._osc_status['messages_sent']} | Queue: {self._osc_status['queue_size']}"
            grid.add_row(stats, "")
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
        
        grid.add_row(
            "[dim]Press Ctrl+C to quit[/dim]",
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
            self._data_stats["samples_processed"] = event.data.get("num_samples", 0)
            self._update_layout()

    def _on_status_update(self, event: Event) -> None:
        """Handle status update events."""
        if event.data and event.data.get("type") == "channel_discovery_complete":
            # Channel discovery completed
            self._channel_info.update({
                "discovery_mode": False,
                "total_channels": event.data.get("total_channels", 0),
                "discovered_channels": event.data.get("discovered_channels", []),
                "channel_list": event.data.get("channel_info", [])
            })
            
            # Show completion message
            self.show_message(f"Channel discovery complete! Found {self._channel_info['total_channels']} channels.", "info")
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