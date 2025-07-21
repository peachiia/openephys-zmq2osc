from rich.console import Console
from rich.layout import Layout
from rich.theme import Theme
from rich.panel import Panel
from rich.table import Table
from datetime import datetime
from rich.live import Live
from rich.rule import Rule

# import delay using time
import time



class Ui:

    custom_theme = Theme({
        "val_success": "bold green",
        "val_error": "bold red",
        "default": "orange1",
        "grid_rule": "dim",
    })


    class HeaderPanel:
        def __init__(self, ui):
            self.apps_name = ui.apps_name
            self.apps_version = ui.apps_version

        def __rich__(self) -> Panel:
            grid = Table.grid(expand=True)
            grid.add_column(justify="center", ratio=1)
            grid.add_column(justify="right")
            grid.add_row(
                f"[b]{self.apps_name}[/b] [dim]v{self.apps_version}[/dim]",
                datetime.now().ctime().replace(":", "[blink]:[/]"),
            )
            return Panel(grid, style="default")
        
    
    class ZmqPanel:
        def __init__(self, ui):
            # param = ui.param
            self.panel_name = "ZMQ (OpenEphys Server)"

        def __rich__(self) -> Panel:
            grid = Table.grid(expand=True)
            grid.add_column(justify="left", ratio=1)
            grid.add_column(justify="left", ratio=2)

            grid.add_row(
               "AppsName",
                "apps",
            )
            grid.add_row(
               "UUID",
                "e89b",
            )
            grid.add_row(
               "Address",
                "localhost",
            )
            grid.add_row(
               "DataPort",
                "5556",
            )
            grid.add_row(Rule(style="grid_rule"),Rule(style="grid_rule"))
            
            grid.add_row(
               "[dim][i]Ident.[/i][/dim]",
                "[dim][i]apps-e89b[/i][/dim]",
            )
            grid.add_row(
                "[dim][i]HBPort[/i][/dim]",
                "[dim][i]5557 (DP+1)[/i][/dim]",
            )
            grid.add_row()
            grid.add_row(
                "Status",
                "Retrying connection...",
            )
            grid.add_row(Rule(style="default"),Rule(style="default"))
            grid.add_row(
                "No Data",
            )
            return Panel(grid, title=self.panel_name, border_style="default")
        

    class OscPanel:
        def __init__(self, ui):
            # param = ui.param
            self.panel_name = "OSC"

        def __rich__(self) -> Panel:
            grid = Table.grid(expand=True)
            grid.add_column(justify="left", ratio=1)
            grid.add_column(justify="left", ratio=2)

            grid.add_row(
               "Address",
                "localhost",
            )
            grid.add_row(
               "Port",
                "10000",
            )
            grid.add_row("",Rule(style="grid_rule"))
            grid.add_row(
               "Channel",
                "32",
            )
            grid.add_row(
                "SampleRate",
                "30000",
            )
            

            grid.add_row(Rule(style="grid_rule"),Rule(style="grid_rule"))

            grid.add_row(
                "Status",
                "Retrying connection...",
            )
            grid.add_row(Rule(style="default"),Rule(style="default"))
            grid.add_row(
                "No Data",
            )
            return Panel(grid, title=self.panel_name, border_style="default")
        
        
        

    def __init__(self):
        self.__is_running = True

        self.console = Console(theme=self.custom_theme)
        self.apps_name = "OpenEphys - ZMQ to OSC"
        self.apps_version = "0.1.0"

        self.layout = self.init_layout()
        self.layout["header"].update(Ui.HeaderPanel(self))
        self.layout["left"].update(Ui.ZmqPanel(self))
        self.layout["right"].update(Ui.OscPanel(self))


    def init_layout(self) -> Layout:
        """Define the layout."""
        layout = Layout(name="root")

        layout.split(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        #loayout["side"].split(Layout(name="box1"), Layout(name="box2"))
        # by default, collapsed the body
        #layout["body"].visible
        return layout

    def clear(self):
        self.console.clear()


    def render(self):
        """
        Render text in the console with optional styling.
        :param text: The text to render.
        :param style: Optional style for the text.
        """
        #self.draw_appsname("App Name")
        #print(self.layout)

        with Live(self.layout, console=self.console, auto_refresh=True, screen=True, refresh_per_second=10):
            while self.__is_running:
                time.sleep(0.1)  # Simulate some processing delay
                pass

    def stop(self):
        """
        Stop the UI rendering.
        """
        self.__is_running = False

if __name__ == "__main__":
    ui = Ui()
    ui.clear()
    ui.render()
