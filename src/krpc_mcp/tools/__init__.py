"""MCP tool modules for kRPC control surfaces."""

from .vessel import register_vessel_tools
from .flight import register_flight_tools
from .orbit import register_orbit_tools
from .resources import register_resource_tools

__all__ = [
    "register_vessel_tools",
    "register_flight_tools",
    "register_orbit_tools",
    "register_resource_tools",
]
