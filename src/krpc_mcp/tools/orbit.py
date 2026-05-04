"""MCP tools for orbital mechanics: orbit state, maneuver nodes, warp."""

from mcp.server import Server
from mcp.types import TextContent
from ..connection import get_connection


def register_orbit_tools(server: Server) -> None:
    @server.tool()
    def get_orbit_info() -> list[TextContent]:
        """Return the active vessel's current orbital parameters."""
        conn = get_connection()
        orbit = conn.space_center.active_vessel.orbit
        return [TextContent(
            type="text",
            text=(
                f"Body: {orbit.body.name}\n"
                f"Apoapsis (m): {orbit.apoapsis_altitude:.0f}\n"
                f"Periapsis (m): {orbit.periapsis_altitude:.0f}\n"
                f"Semi-major axis (m): {orbit.semi_major_axis:.0f}\n"
                f"Eccentricity: {orbit.eccentricity:.6f}\n"
                f"Inclination (°): {orbit.inclination:.3f}\n"
                f"LAN (°): {orbit.longitude_of_ascending_node:.3f}\n"
                f"Arg of periapsis (°): {orbit.argument_of_periapsis:.3f}\n"
                f"Mean anomaly at epoch (°): {orbit.mean_anomaly_at_epoch:.6f}\n"
                f"Period (s): {orbit.period:.1f}\n"
                f"Time to Ap (s): {orbit.time_to_apoapsis:.1f}\n"
                f"Time to Pe (s): {orbit.time_to_periapsis:.1f}\n"
                f"Orbital speed (m/s): {orbit.orbital_speed:.1f}\n"
            ),
        )]

    @server.tool()
    def add_maneuver_node(
        ut: float,
        prograde: float = 0.0,
        normal: float = 0.0,
        radial: float = 0.0,
    ) -> list[TextContent]:
        """Add a maneuver node at the given universal time.

        Args:
            ut: Universal time (seconds since epoch) for the burn.
            prograde: Delta-v in the prograde direction (m/s).
            normal: Delta-v in the normal direction (m/s).
            radial: Delta-v in the radial direction (m/s).
        """
        conn = get_connection()
        vessel = conn.space_center.active_vessel
        node = vessel.control.add_node(ut, prograde=prograde, normal=normal, radial=radial)
        dv = (prograde**2 + normal**2 + radial**2) ** 0.5
        return [TextContent(
            type="text",
            text=(
                f"Maneuver node added.\n"
                f"UT: {node.ut:.1f}\n"
                f"Delta-V magnitude: {dv:.2f} m/s\n"
                f"Prograde: {prograde:.2f} m/s\n"
                f"Normal: {normal:.2f} m/s\n"
                f"Radial: {radial:.2f} m/s\n"
            ),
        )]

    @server.tool()
    def remove_all_maneuver_nodes() -> list[TextContent]:
        """Remove all maneuver nodes from the active vessel."""
        conn = get_connection()
        for node in conn.space_center.active_vessel.control.nodes:
            node.remove()
        return [TextContent(type="text", text="All maneuver nodes removed.")]

    @server.tool()
    def warp_to(ut: float) -> list[TextContent]:
        """Time-warp to the given universal time.

        Args:
            ut: Target universal time in seconds since epoch.
        """
        conn = get_connection()
        conn.space_center.warp_to(ut)
        current = conn.space_center.ut
        return [TextContent(type="text", text=f"Warp complete. UT is now {current:.1f}.")]

    @server.tool()
    def get_universal_time() -> list[TextContent]:
        """Return the current universal time and mission-elapsed time."""
        conn = get_connection()
        sc = conn.space_center
        ut = sc.ut
        met = sc.active_vessel.met
        return [TextContent(
            type="text",
            text=f"Universal time (s): {ut:.1f}\nMission elapsed time (s): {met:.1f}",
        )]
