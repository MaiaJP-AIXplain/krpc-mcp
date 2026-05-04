"""MCP tools for vessel state and info."""

from mcp.server import Server
from mcp.types import Tool, TextContent
from ..connection import get_connection


def register_vessel_tools(server: Server) -> None:
    @server.tool()
    def get_vessel_info() -> list[TextContent]:
        """Return the active vessel's name, situation, biome, mass, and crew."""
        conn = get_connection()
        vessel = conn.space_center.active_vessel
        flight = vessel.flight()
        return [TextContent(
            type="text",
            text=(
                f"Name: {vessel.name}\n"
                f"Type: {vessel.type}\n"
                f"Situation: {vessel.situation}\n"
                f"Biome: {vessel.biome}\n"
                f"Met (s): {vessel.met:.1f}\n"
                f"Mass (kg): {vessel.mass:.1f}\n"
                f"Dry mass (kg): {vessel.dry_mass:.1f}\n"
                f"Crew count: {vessel.crew_count} / {vessel.crew_capacity}\n"
                f"Altitude ASL (m): {flight.mean_altitude:.1f}\n"
                f"Altitude AGL (m): {flight.surface_altitude:.1f}\n"
                f"Speed (m/s): {flight.speed:.1f}\n"
                f"Vertical speed (m/s): {flight.vertical_speed:.1f}\n"
            ),
        )]

    @server.tool()
    def list_vessels() -> list[TextContent]:
        """List all vessels currently tracked by the Space Center."""
        conn = get_connection()
        vessels = conn.space_center.vessels
        lines = []
        for v in vessels:
            lines.append(f"- {v.name} ({v.type}) — {v.situation}")
        return [TextContent(type="text", text="\n".join(lines) if lines else "No vessels found.")]

    @server.tool()
    def set_active_vessel(vessel_name: str) -> list[TextContent]:
        """Switch focus to the vessel with the given name.

        Args:
            vessel_name: Exact name of the vessel to focus.
        """
        conn = get_connection()
        for v in conn.space_center.vessels:
            if v.name == vessel_name:
                conn.space_center.active_vessel = v
                return [TextContent(type="text", text=f"Switched to vessel: {v.name}")]
        return [TextContent(type="text", text=f"Vessel not found: {vessel_name}")]
