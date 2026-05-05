"""Curated kRPC → MCP bridge.

At startup, calls conn.krpc.get_services() to obtain the kRPC service schema,
then registers the focused procedure set an AI copilot needs for vessel
telemetry, flight control, mission planning, and MechJeb automation.  Set
``KRPC_MCP_TOOL_MODE=full`` to expose every supported kRPC procedure for
debugging.  Class-member procedures (those with a leading 'this' parameter)
accept an integer instance_id so the caller can chain object references across
tool calls.

Class proxy resolution: kRPC Python uses two code-gen strategies depending on
how the service was loaded.

  1. *Static* services (e.g. ``SpaceCenter``): each generated proxy class is a
     top-level member of the service's generated module — ``Vessel`` lives at
     ``krpc.services.spacecenter.Vessel``.
  2. *Dynamic* services (e.g. the ``MechJeb`` extension service): proxy
     classes are attached as attributes on the service *type* itself
     (``type(conn.mech_jeb).ManeuverPlanner``); the service type's
     ``__module__`` is ``krpc.service``, the runtime base, not a generated
     module.

In both cases, generated proxies share the same ``__init__(client, object_id)``
signature.  ``_class_proxy`` searches the static module first (the common
case) and falls back to the service type's attributes for dynamic services.
"""

import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from typing import Any

import krpc.error
from mcp.server import Server
from mcp.types import TextContent, Tool

from .connection import get_connection
from .type_mapper import (
    SKIP_TYPE_CODES,
    TC_EVENT,
    TC_PROCEDURE_CALL,
    TC_SERVICES,
    TC_STATUS,
    TC_STREAM,
    format_result,
    params_to_input_schema,
    strip_xml,
)

MECHJEB_SERVICE = "MechJeb"

_TYPE_CODE_NAMES: dict[int, str] = {
    TC_EVENT: "TC_EVENT",
    TC_PROCEDURE_CALL: "TC_PROCEDURE_CALL",
    TC_STREAM: "TC_STREAM",
    TC_STATUS: "TC_STATUS",
    TC_SERVICES: "TC_SERVICES",
}

logger = logging.getLogger(__name__)

_MUTATING_PREFIXES: tuple[str, ...] = (
    "set_",
    "activate",
    "warp",
    "launch",
    "recover",
    "save",
    "load",
    "quick",
    "revert",
    "dock",
    "undock",
    "decouple",
    "stage",
)

_FULL_TOOL_MODE_VALUES = {"full", "all", "debug"}

_CURATED_SPACE_CENTER_TOOLS: frozenset[str] = frozenset(
    {
        "space_center_get_ut",
        "space_center_clear_target",
        "space_center_get_active_vessel",
        "space_center_get_bodies",
        "space_center_get_target_body",
        "space_center_get_vessels",
        "space_center_set_active_vessel",
        "space_center_set_target_body",
        "space_center_warp_to",
        "space_center_celestial_body_get_atmosphere_depth",
        "space_center_celestial_body_get_equatorial_radius",
        "space_center_celestial_body_get_has_atmosphere",
        "space_center_celestial_body_get_has_solid_surface",
        "space_center_celestial_body_get_name",
        "space_center_celestial_body_get_orbit",
        "space_center_celestial_body_get_sphere_of_influence",
        "space_center_celestial_body_get_surface_gravity",
        "space_center_vessel_get_name",
        "space_center_vessel_get_met",
        "space_center_vessel_get_mass",
        "space_center_vessel_get_situation",
        "space_center_vessel_get_surface_reference_frame",
        "space_center_vessel_get_control",
        "space_center_control_get_throttle",
        "space_center_control_set_throttle",
        "space_center_control_get_sas",
        "space_center_control_set_sas",
        "space_center_control_get_sas_mode",
        "space_center_control_set_sas_mode",
        "space_center_control_get_rcs",
        "space_center_control_set_rcs",
        "space_center_control_get_gear",
        "space_center_control_set_gear",
        "space_center_control_get_brakes",
        "space_center_control_set_brakes",
        "space_center_control_activate_next_stage",
        "space_center_control_add_node",
        "space_center_control_get_nodes",
        "space_center_control_remove_nodes",
        "space_center_node_get_ut",
        "space_center_node_set_ut",
        "space_center_node_get_prograde",
        "space_center_node_set_prograde",
        "space_center_node_get_normal",
        "space_center_node_set_normal",
        "space_center_node_get_radial",
        "space_center_node_set_radial",
        "space_center_node_remove",
        "space_center_vessel_get_auto_pilot",
        "space_center_auto_pilot_engage",
        "space_center_auto_pilot_disengage",
        "space_center_auto_pilot_get_target_pitch",
        "space_center_auto_pilot_set_target_pitch",
        "space_center_auto_pilot_set_target_heading",
        "space_center_auto_pilot_set_target_roll",
        "space_center_auto_pilot_target_pitch_and_heading",
        "space_center_auto_pilot_get_error",
        "space_center_vessel_get_flight",
        "space_center_flight_get_altitude",
        "space_center_flight_get_mean_altitude",
        "space_center_flight_get_surface_altitude",
        "space_center_flight_get_latitude",
        "space_center_flight_get_longitude",
        "space_center_flight_get_speed",
        "space_center_flight_get_vertical_speed",
        "space_center_flight_get_horizontal_speed",
        "space_center_flight_get_heading",
        "space_center_flight_get_pitch",
        "space_center_flight_get_roll",
        "space_center_flight_get_g_force",
        "space_center_vessel_get_orbit",
        "space_center_orbit_get_apoapsis_altitude",
        "space_center_orbit_get_periapsis_altitude",
        "space_center_orbit_get_eccentricity",
        "space_center_orbit_get_inclination",
        "space_center_orbit_get_period",
        "space_center_orbit_get_time_to_apoapsis",
        "space_center_orbit_get_time_to_periapsis",
        "space_center_orbit_get_semi_major_axis",
        "space_center_orbit_get_orbital_speed",
        "space_center_vessel_get_resources",
        "space_center_resources_get_names",
        "space_center_resources_amount",
        "space_center_resources_max",
    }
)

_CURATED_MECHJEB_TOOLS: frozenset[str] = frozenset(
    {
        "mech_jeb_get_api_ready",
        "mech_jeb_get_ascent_autopilot",
        "mech_jeb_get_landing_autopilot",
        "mech_jeb_get_docking_autopilot",
        "mech_jeb_get_rendezvous_autopilot",
        "mech_jeb_get_node_executor",
        "mech_jeb_get_maneuver_planner",
        "mech_jeb_get_smart_ass",
        "mech_jeb_get_target_controller",
        "mech_jeb_get_thrust_controller",
        "mech_jeb_get_staging_controller",
        "mech_jeb_get_rcs_controller",
        "mech_jeb_ascent_autopilot_get_enabled",
        "mech_jeb_ascent_autopilot_set_enabled",
        "mech_jeb_ascent_autopilot_get_status",
        "mech_jeb_ascent_autopilot_get_desired_orbit_altitude",
        "mech_jeb_ascent_autopilot_set_desired_orbit_altitude",
        "mech_jeb_ascent_autopilot_get_desired_inclination",
        "mech_jeb_ascent_autopilot_set_desired_inclination",
        "mech_jeb_ascent_autopilot_launch_to_rendezvous",
        "mech_jeb_ascent_autopilot_launch_to_target_plane",
        "mech_jeb_landing_autopilot_get_enabled",
        "mech_jeb_landing_autopilot_set_enabled",
        "mech_jeb_landing_autopilot_get_status",
        "mech_jeb_landing_autopilot_land_untargeted",
        "mech_jeb_landing_autopilot_land_at_position_target",
        "mech_jeb_landing_autopilot_stop_landing",
        "mech_jeb_landing_autopilot_get_touchdown_speed",
        "mech_jeb_landing_autopilot_set_touchdown_speed",
        "mech_jeb_docking_autopilot_get_enabled",
        "mech_jeb_docking_autopilot_set_enabled",
        "mech_jeb_docking_autopilot_get_status",
        "mech_jeb_docking_autopilot_get_speed_limit",
        "mech_jeb_docking_autopilot_set_speed_limit",
        "mech_jeb_rendezvous_autopilot_get_enabled",
        "mech_jeb_rendezvous_autopilot_set_enabled",
        "mech_jeb_rendezvous_autopilot_get_status",
        "mech_jeb_rendezvous_autopilot_get_desired_distance",
        "mech_jeb_rendezvous_autopilot_set_desired_distance",
        "mech_jeb_node_executor_get_enabled",
        "mech_jeb_node_executor_get_autowarp",
        "mech_jeb_node_executor_set_autowarp",
        "mech_jeb_node_executor_execute_one_node",
        "mech_jeb_node_executor_execute_all_nodes",
        "mech_jeb_node_executor_abort",
        "mech_jeb_maneuver_planner_get_operation_circularize",
        "mech_jeb_maneuver_planner_get_operation_apoapsis",
        "mech_jeb_maneuver_planner_get_operation_course_correction",
        "mech_jeb_maneuver_planner_get_operation_periapsis",
        "mech_jeb_maneuver_planner_get_operation_inclination",
        "mech_jeb_maneuver_planner_get_operation_interplanetary_transfer",
        "mech_jeb_maneuver_planner_get_operation_lambert",
        "mech_jeb_maneuver_planner_get_operation_plane",
        "mech_jeb_maneuver_planner_get_operation_transfer",
        "mech_jeb_operation_circularize_make_node",
        "mech_jeb_operation_circularize_make_nodes",
        "mech_jeb_operation_apoapsis_get_new_apoapsis",
        "mech_jeb_operation_apoapsis_set_new_apoapsis",
        "mech_jeb_operation_apoapsis_make_node",
        "mech_jeb_operation_apoapsis_make_nodes",
        "mech_jeb_operation_periapsis_get_new_periapsis",
        "mech_jeb_operation_periapsis_set_new_periapsis",
        "mech_jeb_operation_periapsis_make_node",
        "mech_jeb_operation_periapsis_make_nodes",
        "mech_jeb_operation_course_correction_get_course_correct_final_pe_a",
        "mech_jeb_operation_course_correction_set_course_correct_final_pe_a",
        "mech_jeb_operation_course_correction_get_intercept_distance",
        "mech_jeb_operation_course_correction_set_intercept_distance",
        "mech_jeb_operation_course_correction_make_node",
        "mech_jeb_operation_course_correction_make_nodes",
        "mech_jeb_operation_inclination_get_new_inclination",
        "mech_jeb_operation_inclination_set_new_inclination",
        "mech_jeb_operation_inclination_make_node",
        "mech_jeb_operation_inclination_make_nodes",
        "mech_jeb_operation_interplanetary_transfer_get_wait_for_phase_angle",
        "mech_jeb_operation_interplanetary_transfer_set_wait_for_phase_angle",
        "mech_jeb_operation_interplanetary_transfer_make_node",
        "mech_jeb_operation_interplanetary_transfer_make_nodes",
        "mech_jeb_operation_lambert_get_intercept_interval",
        "mech_jeb_operation_lambert_set_intercept_interval",
        "mech_jeb_operation_lambert_make_node",
        "mech_jeb_operation_lambert_make_nodes",
        "mech_jeb_operation_plane_make_node",
        "mech_jeb_operation_plane_make_nodes",
        "mech_jeb_operation_transfer_get_intercept_only",
        "mech_jeb_operation_transfer_set_intercept_only",
        "mech_jeb_operation_transfer_get_period_offset",
        "mech_jeb_operation_transfer_set_period_offset",
        "mech_jeb_operation_transfer_get_simple_transfer",
        "mech_jeb_operation_transfer_set_simple_transfer",
        "mech_jeb_operation_transfer_make_node",
        "mech_jeb_operation_transfer_make_nodes",
        "mech_jeb_smart_ass_get_autopilot_mode",
        "mech_jeb_smart_ass_set_autopilot_mode",
        "mech_jeb_smart_ass_get_interface_mode",
        "mech_jeb_smart_ass_set_interface_mode",
        "mech_jeb_smart_ass_update",
        "mech_jeb_thrust_controller_get_enabled",
        "mech_jeb_thrust_controller_set_enabled",
        "mech_jeb_thrust_controller_get_limit_acceleration",
        "mech_jeb_thrust_controller_set_limit_acceleration",
        "mech_jeb_staging_controller_get_enabled",
        "mech_jeb_staging_controller_set_enabled",
        "mech_jeb_rcs_controller_get_enabled",
        "mech_jeb_rcs_controller_set_enabled",
        "mech_jeb_target_controller_get_distance",
        "mech_jeb_target_controller_get_relative_velocity",
        "mech_jeb_target_controller_get_target_orbit",
        "mech_jeb_target_controller_get_normal_target_exists",
        "mech_jeb_target_controller_get_position_target_exists",
    }
)

_MISSION_ASSIST_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="mission_assist_flight_snapshot",
        description=(
            "Copilot mission snapshot for the active vessel: handles, control state, "
            "flight telemetry, orbit, resources, and MechJeb readiness when available."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "include_resources": {
                    "type": "boolean",
                    "description": "Include aggregate resource names when available.",
                    "default": True,
                },
                "include_mechjeb": {
                    "type": "boolean",
                    "description": "Include MechJeb readiness when the service is installed.",
                    "default": True,
                },
            },
        },
    ),
    Tool(
        name="mission_assist_plan_goal",
        description=(
            "Turn a natural-language KSP objective into a staged agent playbook using "
            "mission snapshot, MechJeb maneuver planner, node executor, warps, and fallbacks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Mission goal, e.g. 'land this vessel on Duna'.",
                },
                "destination_body": {
                    "type": "string",
                    "description": "Optional destination body name when the objective implies one.",
                },
                "prefer_mechjeb": {
                    "type": "boolean",
                    "description": "Prefer MechJeb planner/executor/autopilots when available.",
                    "default": True,
                },
            },
            "required": ["objective"],
        },
    ),
)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def _to_snake(name: str) -> str:
    """Convert PascalCase / camelCase / ALLCAPS to snake_case."""
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)
    return name.lower()


def _tool_name(service_name: str, proc_name: str) -> str:
    return f"{_to_snake(service_name)}_{_to_snake(proc_name)}"


def _is_mutating_proc(proc_name: str) -> bool:
    """Best-effort guard for procedures that can change game state."""
    lowered = proc_name.lower()
    candidates = [lowered]
    if "_" in lowered:
        candidates.append(lowered.split("_", 1)[1])

    if any(candidate.startswith("get_") for candidate in candidates):
        return False
    return any(candidate.startswith(_MUTATING_PREFIXES) for candidate in candidates)


def _full_tool_mode_enabled() -> bool:
    return os.environ.get("KRPC_MCP_TOOL_MODE", "").strip().lower() in _FULL_TOOL_MODE_VALUES


def _is_curated_tool_name(name: str) -> bool:
    """Return True when a discovered tool belongs in the default copilot surface."""
    if name in _CURATED_SPACE_CENTER_TOOLS:
        return True
    return name in _CURATED_MECHJEB_TOOLS


# ---------------------------------------------------------------------------
# MechJeb readiness guard
# ---------------------------------------------------------------------------

def _check_mechjeb_ready(conn) -> str | None:
    """Return an error string if MechJeb.APIReady is False, else None."""
    try:
        if not conn.mech_jeb.api_ready:
            return (
                "MechJeb.APIReady is false — MechJeb is not initialised. "
                "Ensure the kRPC.MechJeb mod is installed and a vessel is active."
            )
    except AttributeError:
        return "MechJeb service not found on this kRPC connection."
    return None


# ---------------------------------------------------------------------------
# Mission-assist snapshot helpers
# ---------------------------------------------------------------------------

def _object_ref(value: Any) -> int | None:
    object_id = getattr(value, "_object_id", None)
    if object_id is None:
        return None
    try:
        return int(object_id)
    except (TypeError, ValueError):
        return object_id


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _safe_call(obj: Any, name: str, *args: Any, default: Any = None) -> Any:
    try:
        method = getattr(obj, name)
        value = method(*args)
    except Exception:
        return default
    return _object_ref(value) if hasattr(value, "_object_id") else value


def _build_flight_snapshot(
    conn,
    *,
    include_resources: bool,
    include_mechjeb: bool,
) -> dict[str, Any]:
    vessel = conn.space_center.active_vessel
    control = _safe_attr(vessel, "control")
    flight = _safe_attr(vessel, "flight")
    orbit = _safe_attr(vessel, "orbit")
    resources = _safe_attr(vessel, "resources") if include_resources else None

    snapshot: dict[str, Any] = {
        "active_vessel": {
            "id": _object_ref(vessel),
            "name": _safe_attr(vessel, "name"),
            "met": _safe_attr(vessel, "met"),
            "mass": _safe_attr(vessel, "mass"),
            "situation": _safe_attr(vessel, "situation"),
        },
        "handles": {
            "vessel": _object_ref(vessel),
            "control": control if isinstance(control, int) else _object_ref(control),
            "flight": flight if isinstance(flight, int) else _object_ref(flight),
            "orbit": orbit if isinstance(orbit, int) else _object_ref(orbit),
            "resources": resources if isinstance(resources, int) else _object_ref(resources),
        },
    }

    if control is not None and not isinstance(control, int):
        snapshot["control"] = {
            "throttle": _safe_attr(control, "throttle"),
            "sas": _safe_attr(control, "sas"),
            "sas_mode": _safe_attr(control, "sas_mode"),
            "rcs": _safe_attr(control, "rcs"),
            "gear": _safe_attr(control, "gear"),
            "brakes": _safe_attr(control, "brakes"),
        }

    if flight is not None and not isinstance(flight, int):
        snapshot["flight"] = {
            "altitude": _safe_attr(flight, "altitude"),
            "mean_altitude": _safe_attr(flight, "mean_altitude"),
            "surface_altitude": _safe_attr(flight, "surface_altitude"),
            "latitude": _safe_attr(flight, "latitude"),
            "longitude": _safe_attr(flight, "longitude"),
            "speed": _safe_attr(flight, "speed"),
            "vertical_speed": _safe_attr(flight, "vertical_speed"),
            "horizontal_speed": _safe_attr(flight, "horizontal_speed"),
            "heading": _safe_attr(flight, "heading"),
            "pitch": _safe_attr(flight, "pitch"),
            "roll": _safe_attr(flight, "roll"),
            "g_force": _safe_attr(flight, "g_force"),
        }

    if orbit is not None and not isinstance(orbit, int):
        snapshot["orbit"] = {
            "apoapsis_altitude": _safe_attr(orbit, "apoapsis_altitude"),
            "periapsis_altitude": _safe_attr(orbit, "periapsis_altitude"),
            "eccentricity": _safe_attr(orbit, "eccentricity"),
            "inclination": _safe_attr(orbit, "inclination"),
            "period": _safe_attr(orbit, "period"),
            "time_to_apoapsis": _safe_attr(orbit, "time_to_apoapsis"),
            "time_to_periapsis": _safe_attr(orbit, "time_to_periapsis"),
            "semi_major_axis": _safe_attr(orbit, "semi_major_axis"),
            "orbital_speed": _safe_attr(orbit, "orbital_speed"),
        }

    if resources is not None and not isinstance(resources, int):
        snapshot["resources"] = {
            "names": _safe_attr(resources, "names", default=[]),
        }

    if include_mechjeb:
        snapshot["mechjeb"] = {
            "available": hasattr(conn, "mech_jeb"),
            "api_ready": _safe_attr(getattr(conn, "mech_jeb", None), "api_ready"),
        }

    return snapshot


def _infer_destination(objective: str, explicit_destination: str | None) -> str | None:
    if explicit_destination:
        return explicit_destination.strip() or None

    objective_lower = objective.lower()
    for body in (
        "moho",
        "eve",
        "gilly",
        "kerbin",
        "mun",
        "minmus",
        "duna",
        "ike",
        "dres",
        "jool",
        "laythe",
        "vall",
        "tylo",
        "bop",
        "pol",
        "eeloo",
    ):
        if body in objective_lower:
            return body.title()
    return None


def _build_goal_plan(
    conn,
    *,
    objective: str,
    destination_body: str | None,
    prefer_mechjeb: bool,
) -> dict[str, Any]:
    snapshot = _build_flight_snapshot(conn, include_resources=True, include_mechjeb=True)
    destination = _infer_destination(objective, destination_body)
    objective_lower = objective.lower()
    wants_landing = any(word in objective_lower for word in ("land", "landing", "touchdown"))
    wants_interplanetary = destination is not None and destination.lower() not in {
        "kerbin",
        "mun",
        "minmus",
    }
    mechjeb_ready = bool(snapshot.get("mechjeb", {}).get("api_ready"))
    use_mechjeb = prefer_mechjeb and mechjeb_ready

    phases: list[dict[str, Any]] = [
        {
            "name": "baseline_and_target",
            "intent": "Get complete state, identify destination body, and set target context.",
            "tools": [
                "mission_assist_flight_snapshot",
                "space_center_get_bodies",
                "space_center_celestial_body_get_name",
                "space_center_set_target_body",
                "space_center_get_target_body",
            ],
            "notes": [
                "Resolve the destination body handle from space_center_get_bodies.",
                "Confirm the active vessel did not change before planning burns.",
            ],
        },
        {
            "name": "parking_orbit_readiness",
            "intent": "Ensure the vessel is in a controllable, stable state before major planning.",
            "tools": [
                "mission_assist_flight_snapshot",
                "mech_jeb_get_ascent_autopilot",
                "mech_jeb_ascent_autopilot_set_desired_orbit_altitude",
                "mech_jeb_ascent_autopilot_set_enabled",
            ],
            "notes": [
                "If already in stable orbit, skip ascent and move to maneuver planning.",
                "If not in orbit and MechJeb is ready, use ascent autopilot.",
            ],
        },
    ]

    if wants_interplanetary:
        phases.append(
            {
                "name": "interplanetary_transfer",
                "intent": f"Create a transfer from the current system toward {destination}.",
                "tools": [
                    "mech_jeb_get_maneuver_planner",
                    "mech_jeb_maneuver_planner_get_operation_interplanetary_transfer",
                    "mech_jeb_operation_interplanetary_transfer_set_wait_for_phase_angle",
                    "mech_jeb_operation_interplanetary_transfer_make_nodes",
                    "mech_jeb_get_node_executor",
                    "mech_jeb_node_executor_set_autowarp",
                    "mech_jeb_node_executor_execute_one_node",
                ],
                "notes": [
                    "Default wait_for_phase_angle to true unless asked for immediate burn.",
                    "Executor autowarp is preferred over waiting through the transfer window.",
                    "Use execute_one_node first; review before execute_all_nodes.",
                ],
            }
        )
        phases.append(
            {
                "name": "midcourse_correction",
                "intent": "Refine encounter after SOI escape or during the transfer coast.",
                "tools": [
                    "mission_assist_flight_snapshot",
                    "mech_jeb_get_maneuver_planner",
                    "mech_jeb_maneuver_planner_get_operation_course_correction",
                    "mech_jeb_operation_course_correction_set_course_correct_final_pe_a",
                    "mech_jeb_operation_course_correction_make_nodes",
                    "mech_jeb_get_node_executor",
                    "mech_jeb_node_executor_set_autowarp",
                    "mech_jeb_node_executor_execute_one_node",
                ],
                "notes": [
                    "Warp to useful transfer events by default, then re-read the snapshot.",
                    "Tune final periapsis for capture or aerobrake before making correction nodes.",
                ],
            }
        )
        phases.append(
            {
                "name": "arrival_capture",
                "intent": f"Capture into orbit around {destination}.",
                "tools": [
                    "mission_assist_flight_snapshot",
                    "mech_jeb_get_maneuver_planner",
                    "mech_jeb_maneuver_planner_get_operation_periapsis",
                    "mech_jeb_operation_periapsis_set_new_periapsis",
                    "mech_jeb_operation_periapsis_make_nodes",
                    "mech_jeb_maneuver_planner_get_operation_circularize",
                    "mech_jeb_operation_circularize_make_nodes",
                    "mech_jeb_node_executor_execute_one_node",
                ],
                "notes": [
                    "Use destination body atmosphere and periapsis constraints before aerobraking.",
                    "Prefer capture/circularize nodes over manual retrograde burns.",
                ],
            }
        )
    else:
        phases.append(
            {
                "name": "local_orbit_maneuver",
                "intent": "Shape the local orbit with MechJeb planner operations.",
                "tools": [
                    "mech_jeb_get_maneuver_planner",
                    "mech_jeb_maneuver_planner_get_operation_apoapsis",
                    "mech_jeb_maneuver_planner_get_operation_periapsis",
                    "mech_jeb_maneuver_planner_get_operation_circularize",
                    "mech_jeb_get_node_executor",
                    "mech_jeb_node_executor_set_autowarp",
                    "mech_jeb_node_executor_execute_one_node",
                ],
                "notes": [
                    "Use planner operations before manual node creation.",
                    "Warp by default through long stable coasts.",
                ],
            }
        )

    if wants_landing:
        phases.append(
            {
                "name": "descent_and_landing",
                "intent": (
                    f"Land on {destination or 'the target body'} using MechJeb when possible."
                ),
                "tools": [
                    "mission_assist_flight_snapshot",
                    "space_center_celestial_body_get_has_atmosphere",
                    "space_center_celestial_body_get_atmosphere_depth",
                    "space_center_celestial_body_get_surface_gravity",
                    "mech_jeb_get_landing_autopilot",
                    "mech_jeb_landing_autopilot_set_touchdown_speed",
                    "mech_jeb_landing_autopilot_land_untargeted",
                    "mech_jeb_landing_autopilot_get_status",
                    "mech_jeb_landing_autopilot_stop_landing",
                ],
                "notes": [
                    "Use land_at_position_target only after an explicit landing site is selected.",
                    "For atmosphere bodies, plan heat/aerobrake margins before committing descent.",
                    "Abort if target, situation, or vertical speed diverges from expectation.",
                ],
            }
        )

    phases.append(
        {
            "name": "verification_and_next_step",
            "intent": "Close the loop before issuing the next command group.",
            "tools": [
                "mission_assist_flight_snapshot",
                "mech_jeb_node_executor_abort",
                "space_center_control_set_throttle",
            ],
            "notes": [
                "Verify objective progress after every burn, warp, and autopilot mode change.",
                "Keep throttle and executor state explicit when handing off.",
            ],
        }
    )

    return {
        "objective": objective,
        "destination_body": destination,
        "strategy": "mechjeb_first" if use_mechjeb else "direct_krpc_fallback",
        "defaults": {
            "warp_long_waits": True,
            "prefer_node_executor_autowarp": use_mechjeb,
            "prefer_maneuver_planner": use_mechjeb,
            "execute_all_nodes_requires_review": True,
        },
        "current_state": snapshot,
        "phases": phases,
        "fallbacks": [
            "If MechJeb is unavailable or not ready, use space_center_control_add_node, "
            "space_center_warp_to, SAS/RCS, and throttle in small verified steps.",
            "If a planner operation returns a MechJeb operation error, re-read target/body/orbit "
            "state before retrying with different constraints.",
        ],
    }


# ---------------------------------------------------------------------------
# kRPC Python client navigation helpers
# ---------------------------------------------------------------------------

def _service_obj(conn, service_name: str):
    """Return the Python service proxy for a given kRPC service name."""
    if service_name == "KRPC":
        return conn.krpc
    return getattr(conn, _to_snake(service_name))


def _class_proxy(conn, service_name: str, class_name: str, instance_id: int):
    """Reconstruct a kRPC class proxy from its remote object ID.

    See module docstring for the two code-gen strategies kRPC uses. We try
    the static-module location first (the common case for first-party
    services like SpaceCenter), then fall back to attributes on the service
    type itself (extension services like MechJeb).
    """
    svc = _service_obj(conn, service_name)

    # Schemas occasionally report fully-qualified class names like
    # "SpaceCenter.Vessel".  The code generator only exports the leaf name, so
    # try that first; the qualified form is kept as a forward-compat fallback.
    leaf = class_name.rsplit(".", 1)[-1]
    candidates = (leaf,) if leaf == class_name else (leaf, class_name)

    # 1) Static services: proxy classes are module-level members of the
    #    service's generated module (e.g. krpc.services.spacecenter.Vessel).
    module_name = type(svc).__module__
    svc_module = sys.modules.get(module_name)
    if svc_module is not None:
        for candidate in candidates:
            cls = getattr(svc_module, candidate, None)
            if cls is not None:
                return cls(conn, instance_id)

    # 2) Dynamic services (kRPC extensions like MechJeb): proxy classes are
    #    attached as attributes on the service type. Their __init__ shares
    #    the same (client, object_id) shape as static services.
    svc_type = type(svc)
    for candidate in candidates:
        cls = getattr(svc_type, candidate, None)
        if cls is not None and isinstance(cls, type):
            return cls(conn, instance_id)

    raise AttributeError(
        f"kRPC class {class_name!r} not found for service {service_name!r} "
        f"(searched module {module_name!r} and type {svc_type.__name__!r}). "
        "For member procedures, pass the target object's handle "
        "(e.g. Vessel_get_Control returns a Control handle for Control_* calls), "
        "not a vessel handle."
    )


def _infer_class_name(this_param, proc_name: str) -> str:
    """Infer class name for a member procedure from schema metadata or procedure name."""
    t = getattr(this_param, "type", None)
    type_name = getattr(t, "name", "") if t is not None else ""
    if type_name:
        return type_name

    # Fallback for schemas that omit Type.name for the implicit "this" parameter:
    # class member procedures are named "<Class>_<Member>".
    if "_" in proc_name:
        return proc_name.split("_", 1)[0]

    raise ValueError(
        "Missing class metadata for parameter 'this': "
        "cannot infer class name from schema or procedure name."
    )


# ---------------------------------------------------------------------------
# Procedure invocation
# ---------------------------------------------------------------------------

def _call_on(obj, proc_name: str, rest_params, arguments: dict) -> Any:
    """Invoke a kRPC procedure via the Python client's property/method API.

    kRPC Python exposes get_X / set_X procedures as Python properties; all
    other procedures become snake_case methods.
    """
    if proc_name.startswith("get_"):
        return getattr(obj, _to_snake(proc_name[4:]))
    if proc_name.startswith("set_"):
        prop = _to_snake(proc_name[4:])
        param = rest_params[0] if rest_params else None
        value = arguments.get(param.name if param else "value")
        setattr(obj, prop, value)
        return None
    method = getattr(obj, _to_snake(proc_name))
    kwargs = {p.name: arguments[p.name] for p in rest_params if p.name in arguments}
    return method(**kwargs)


def _invoke(conn, service_name: str, proc_name: str, params: list, arguments: dict) -> Any:
    """Dispatch a single kRPC procedure call."""
    this_param = params[0] if params and params[0].name == "this" else None

    if this_param:
        class_name = _infer_class_name(this_param, proc_name)
        instance_id = arguments.get("this")
        if instance_id is None:
            raise ValueError("Missing required parameter 'this' (remote object ID)")
        proxy = _class_proxy(conn, service_name, class_name, int(instance_id))
        # Strip "<ClassName>_" prefix without depending on exact schema class-name formatting.
        bare = proc_name.split("_", 1)[1] if "_" in proc_name else proc_name
        return _call_on(proxy, bare, params[1:], arguments)

    svc = _service_obj(conn, service_name)
    return _call_on(svc, proc_name, params, arguments)


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------

class KrpcBridge:
    """Discovers all kRPC procedures and wires them to an MCP Server instance."""

    def __init__(self) -> None:
        self._conn = None
        self._tools: list[Tool] = []
        # tool_name → (service_name, proc_name, param_list)
        self._registry: dict[str, tuple[str, str, list]] = {}
        self._assist_registry: dict[str, Callable[[dict], list[TextContent]]] = {
            "mission_assist_flight_snapshot": self._mission_assist_flight_snapshot,
            "mission_assist_plan_goal": self._mission_assist_plan_goal,
        }

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _connect_and_discover(self) -> None:
        self._conn = get_connection()
        services_proto = self._conn.krpc.get_services()
        count = 0
        skipped = 0
        hidden = 0
        service_counts: dict[str, int] = {}
        full_tool_mode = _full_tool_mode_enabled()

        for service in services_proto.services:
            svc_count = 0
            for proc in service.procedures:
                reason = self._skip_reason(proc)
                if reason is not None:
                    logger.debug("Skipping %s.%s: %s", service.name, proc.name, reason)
                    skipped += 1
                    continue

                name = _tool_name(service.name, proc.name)
                if not full_tool_mode and not _is_curated_tool_name(name):
                    hidden += 1
                    logger.debug(
                        "Hiding %s.%s: outside curated copilot surface",
                        service.name,
                        proc.name,
                    )
                    continue

                params = list(proc.parameters)
                try:
                    documentation = getattr(proc, "documentation", "")
                except Exception:
                    documentation = ""
                description = (
                    strip_xml(documentation)
                    if documentation
                    else f"{service.name}.{proc.name}"
                )
                input_schema = params_to_input_schema(params)

                self._tools.append(
                    Tool(
                        name=name,
                        description=description[:1024],
                        inputSchema=input_schema,
                    )
                )
                self._registry[name] = (service.name, proc.name, params)
                count += 1
                svc_count += 1

            if svc_count:
                service_counts[service.name] = svc_count

        self._tools.extend(_MISSION_ASSIST_TOOLS)
        count += len(_MISSION_ASSIST_TOOLS)
        service_counts["MissionAssist"] = len(_MISSION_ASSIST_TOOLS)

        if logger.isEnabledFor(logging.DEBUG):
            breakdown = ", ".join(f"{svc}: {n} tools" for svc, n in service_counts.items())
            logger.debug("kRPC bridge per-service counts: %s", breakdown)

        n_services = len(services_proto.services)
        logger.info(
            "kRPC bridge: registered %d tools from %d services (%d skipped, %d hidden)",
            count,
            n_services,
            skipped,
            hidden,
        )

    @staticmethod
    def _skip_reason(proc) -> str | None:
        """Return a human-readable skip reason if the procedure cannot be exposed, else None."""
        if proc.return_type.code in SKIP_TYPE_CODES:
            code_name = _TYPE_CODE_NAMES.get(proc.return_type.code, str(proc.return_type.code))
            return f"unsupported return type {code_name}"
        for p in proc.parameters:
            if p.type.code in SKIP_TYPE_CODES:
                code_name = _TYPE_CODE_NAMES.get(p.type.code, str(p.type.code))
                return f"unsupported param type {code_name} on '{p.name}'"
        return None

    def _ensure_ready(self) -> None:
        if self._conn is None:
            self._connect_and_discover()

    # ------------------------------------------------------------------
    # Public API consumed by the MCP handlers
    # ------------------------------------------------------------------

    def list_tools(self) -> list[Tool]:
        self._ensure_ready()
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> list[TextContent]:
        self._ensure_ready()
        assist_handler = self._assist_registry.get(name)
        if assist_handler is not None:
            return assist_handler(arguments or {})

        entry = self._registry.get(name)
        if entry is None:
            return [TextContent(type="text", text=f"Unknown tool: {name!r}")]
        service_name, proc_name, params = entry

        read_only_mode = (
            os.environ.get("KRPC_MCP_READ_ONLY", "").strip().lower()
            in {"1", "true", "yes"}
        )
        if read_only_mode and _is_mutating_proc(proc_name):
            return [
                TextContent(
                    type="text",
                    text=(
                        f"[{name}] blocked by read-only mode: {service_name}.{proc_name} "
                        "is mutating and disabled (KRPC_MCP_READ_ONLY=1)."
                    ),
                )
            ]

        # Guard: verify MechJeb is initialised before any MechJeb call except APIReady itself.
        if service_name == MECHJEB_SERVICE and proc_name != "get_APIReady":
            err = _check_mechjeb_ready(self._conn)
            if err:
                return [TextContent(type="text", text=err)]

        logger.debug("[bridge] call_tool %s args=%s", name, list((arguments or {}).keys()))
        t0 = time.monotonic()
        try:
            result = _invoke(self._conn, service_name, proc_name, params, arguments or {})
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.debug("[bridge] call_tool %s elapsed=%dms", name, elapsed_ms)
            return [TextContent(type="text", text=format_result(result))]
        except ValueError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "[bridge] call_tool %s bad input elapsed=%dms: %s",
                name,
                elapsed_ms,
                exc,
            )
            return [TextContent(type="text", text=f"[{name}] bad input: {exc}")]
        except krpc.error.RPCError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            msg = str(exc)
            logger.error("[bridge] call_tool %s kRPC error elapsed=%dms: %s", name, elapsed_ms, msg)
            if "OperationException" in msg:
                return [TextContent(type="text", text=f"[{name}] MechJeb operation error: {msg}")]
            return [TextContent(type="text", text=f"[{name}] kRPC RPC error: {msg}")]
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.exception(
                "[bridge] call_tool %s unexpected error elapsed=%dms",
                name,
                elapsed_ms,
            )
            return [TextContent(type="text", text=f"[{name}] kRPC error: {exc}")]

    # ------------------------------------------------------------------
    # MCP Server wiring
    # ------------------------------------------------------------------

    def attach(self, server: Server) -> None:
        """Register list_tools and call_tool handlers on the given MCP Server."""
        bridge = self

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return bridge.list_tools()

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
            return bridge.call_tool(name, arguments)

    # ------------------------------------------------------------------
    # Mission assist tools
    # ------------------------------------------------------------------

    def _mission_assist_flight_snapshot(self, arguments: dict) -> list[TextContent]:
        include_resources = arguments.get("include_resources", True)
        include_mechjeb = arguments.get("include_mechjeb", True)

        try:
            snapshot = _build_flight_snapshot(
                self._conn,
                include_resources=bool(include_resources),
                include_mechjeb=bool(include_mechjeb),
            )
        except Exception as exc:
            logger.exception("mission_assist_flight_snapshot failed")
            return [
                TextContent(
                    type="text",
                    text=f"[mission_assist_flight_snapshot] kRPC error: {exc}",
                )
            ]

        return [TextContent(type="text", text=json.dumps(snapshot, default=str, sort_keys=True))]

    def _mission_assist_plan_goal(self, arguments: dict) -> list[TextContent]:
        objective = str(arguments.get("objective", "")).strip()
        if not objective:
            return [
                TextContent(
                    type="text",
                    text="[mission_assist_plan_goal] bad input: objective is required",
                )
            ]

        destination_body = arguments.get("destination_body")
        prefer_mechjeb = arguments.get("prefer_mechjeb", True)

        try:
            plan = _build_goal_plan(
                self._conn,
                objective=objective,
                destination_body=str(destination_body) if destination_body else None,
                prefer_mechjeb=bool(prefer_mechjeb),
            )
        except Exception as exc:
            logger.exception("mission_assist_plan_goal failed")
            return [
                TextContent(
                    type="text",
                    text=f"[mission_assist_plan_goal] kRPC error: {exc}",
                )
            ]

        return [TextContent(type="text", text=json.dumps(plan, default=str, sort_keys=True))]
