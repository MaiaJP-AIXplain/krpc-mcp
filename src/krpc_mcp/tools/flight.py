"""MCP tools for flight controls: throttle, SAS, RCS, staging, autopilot."""

from mcp.server import Server
from mcp.types import TextContent
from ..connection import get_connection


def register_flight_tools(server: Server) -> None:
    @server.tool()
    def set_throttle(value: float) -> list[TextContent]:
        """Set engine throttle (0.0 = off, 1.0 = full).

        Args:
            value: Throttle level between 0.0 and 1.0.
        """
        value = max(0.0, min(1.0, value))
        conn = get_connection()
        conn.space_center.active_vessel.control.throttle = value
        return [TextContent(type="text", text=f"Throttle set to {value:.2f}")]

    @server.tool()
    def activate_next_stage() -> list[TextContent]:
        """Activate the next staging event on the active vessel."""
        conn = get_connection()
        conn.space_center.active_vessel.control.activate_next_stage()
        return [TextContent(type="text", text="Next stage activated.")]

    @server.tool()
    def set_sas(enabled: bool) -> list[TextContent]:
        """Enable or disable SAS (stability assist system).

        Args:
            enabled: True to enable SAS, False to disable.
        """
        conn = get_connection()
        conn.space_center.active_vessel.control.sas = enabled
        return [TextContent(type="text", text=f"SAS {'enabled' if enabled else 'disabled'}.")]

    @server.tool()
    def set_rcs(enabled: bool) -> list[TextContent]:
        """Enable or disable RCS (reaction control system).

        Args:
            enabled: True to enable RCS, False to disable.
        """
        conn = get_connection()
        conn.space_center.active_vessel.control.rcs = enabled
        return [TextContent(type="text", text=f"RCS {'enabled' if enabled else 'disabled'}.")]

    @server.tool()
    def set_gear(deployed: bool) -> list[TextContent]:
        """Deploy or retract landing gear.

        Args:
            deployed: True to deploy gear, False to retract.
        """
        conn = get_connection()
        conn.space_center.active_vessel.control.gear = deployed
        return [TextContent(type="text", text=f"Gear {'deployed' if deployed else 'retracted'}.")]

    @server.tool()
    def set_brakes(active: bool) -> list[TextContent]:
        """Apply or release wheel brakes.

        Args:
            active: True to apply brakes, False to release.
        """
        conn = get_connection()
        conn.space_center.active_vessel.control.brakes = active
        return [TextContent(type="text", text=f"Brakes {'applied' if active else 'released'}.")]

    @server.tool()
    def set_autopilot_target_pitch_heading(
        pitch: float,
        heading: float,
    ) -> list[TextContent]:
        """Point the vessel to the given pitch and heading using the stock autopilot.

        Args:
            pitch: Target pitch in degrees (-90 to 90, positive = up).
            heading: Target heading in degrees (0 = north, 90 = east).
        """
        conn = get_connection()
        ap = conn.space_center.active_vessel.auto_pilot
        ap.target_pitch = pitch
        ap.target_heading = heading
        ap.engage()
        return [TextContent(type="text", text=f"Autopilot engaged: pitch={pitch:.1f}°, heading={heading:.1f}°")]

    @server.tool()
    def disengage_autopilot() -> list[TextContent]:
        """Disengage the stock autopilot."""
        conn = get_connection()
        conn.space_center.active_vessel.auto_pilot.disengage()
        return [TextContent(type="text", text="Autopilot disengaged.")]
