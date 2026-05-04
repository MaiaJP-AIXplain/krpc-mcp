"""MCP tools for resource monitoring: fuel, electricity, monoprop."""

from mcp.server import Server
from mcp.types import TextContent
from ..connection import get_connection


def register_resource_tools(server: Server) -> None:
    @server.tool()
    def get_resources() -> list[TextContent]:
        """Return the active vessel's current resource amounts and capacities."""
        conn = get_connection()
        resources = conn.space_center.active_vessel.resources
        names = resources.names
        if not names:
            return [TextContent(type="text", text="No resources found on vessel.")]

        lines = []
        for name in names:
            amount = resources.amount(name)
            capacity = resources.max(name)
            pct = (amount / capacity * 100) if capacity > 0 else 0
            lines.append(f"- {name}: {amount:.1f} / {capacity:.1f} ({pct:.1f}%)")
        return [TextContent(type="text", text="\n".join(lines))]

    @server.tool()
    def get_resource_amount(resource_name: str) -> list[TextContent]:
        """Return the amount and capacity of a specific resource.

        Args:
            resource_name: Resource name, e.g. 'LiquidFuel', 'Oxidizer', 'ElectricCharge'.
        """
        conn = get_connection()
        resources = conn.space_center.active_vessel.resources
        try:
            amount = resources.amount(resource_name)
            capacity = resources.max(resource_name)
            pct = (amount / capacity * 100) if capacity > 0 else 0
            return [TextContent(
                type="text",
                text=f"{resource_name}: {amount:.1f} / {capacity:.1f} ({pct:.1f}%)",
            )]
        except Exception:
            return [TextContent(type="text", text=f"Resource not found: {resource_name}")]
