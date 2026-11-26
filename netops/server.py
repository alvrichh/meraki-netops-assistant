"""Minimal MCP server over stdio, using only the Python standard library.

Claude Code starts it from .mcp.json and talks JSON-RPC 2.0, one message per
line. It implements the parts of the Model Context Protocol a tools-only
server needs: initialize, tools/list, tools/call and ping.
"""

import io
import json
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):
    # Allow "python3 netops/server.py" as well as "python3 -m netops.server".
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from netops import __version__
from netops.data import DemoOrg, NetworkNotFound

SERVER_NAME = "meraki-demo"
# Newest first. initialize answers with the client's version if listed, otherwise the newest.
SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

NETWORK_ARG = {
    "type": "string",
    "description": "Network name (or part of it, e.g. 'dublin') or network id (e.g. 'N_1001').",
}

TOOLS = [
    {
        "name": "list_networks",
        "description": "List every network (office) in the Meraki organisation, with its time zone, tags and ISP circuits.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "network_health_summary",
        "description": "Check one network, or all of them, and return its status (healthy, degraded or down) "
                       "with findings sorted by severity and a suggested next action for each.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}},
    },
    {
        "name": "get_device_statuses",
        "description": "Status of Meraki devices (MX appliances, MS switches, MR access points): online, offline, "
                       "alerting or dormant, with last report time and IPs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "network": NETWORK_ARG,
                "status": {"type": "string", "enum": ["online", "offline", "alerting", "dormant"]},
            },
        },
    },
    {
        "name": "get_uplink_statuses",
        "description": "WAN uplink status of each MX appliance (wan1, wan2, wan3, cellular): active, ready, connecting, "
                       "failed or not connected, plus its high-availability role.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}},
    },
    {
        "name": "get_network_clients",
        "description": "Clients seen on a network, with IP, VLAN, SSID, the device each one was last seen on (recentDeviceName) and usage in KB.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}, "required": ["network"]},
    },
    {
        "name": "get_network_events",
        "description": "Event log of a network, newest first. Optional filter by event type "
                       "(e.g. dhcp_no_leases, disassociation, uplink_change, device_offline).",
        "inputSchema": {
            "type": "object",
            "properties": {"network": NETWORK_ARG, "event_type": {"type": "string"}},
            "required": ["network"],
        },
    },
    {
        "name": "get_channel_utilization",
        "description": "Wi-Fi channel utilisation per access point and radio (wifi0 = first radio, wifi1 = second), "
                       "split into Wi-Fi traffic and non-Wi-Fi interference, in percent, with the sample window.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}, "required": ["network"]},
    },
    {
        "name": "get_vlans",
        "description": "VLANs configured on a network's MX appliance, with subnet, gateway IP and number of usable host addresses.",
        "inputSchema": {"type": "object", "properties": {"network": NETWORK_ARG}, "required": ["network"]},
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}
TOOL_SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in TOOLS}


def call_tool(org, name, arguments):
    """Run one tool and return its result as a JSON-serialisable object."""
    args = arguments or {}
    if name == "list_networks":
        return {"organization": org.organization(), "networks": org.networks()}
    if name == "network_health_summary":
        return org.health_summary(args.get("network"))
    if name == "get_device_statuses":
        return org.device_statuses(args.get("network"), args.get("status"))
    if name == "get_uplink_statuses":
        return org.uplink_statuses(args.get("network"))
    if name == "get_network_clients":
        return org.clients(args["network"])
    if name == "get_network_events":
        return org.events(args["network"], args.get("event_type"))
    if name == "get_channel_utilization":
        return org.channel_utilization(args["network"])
    if name == "get_vlans":
        return org.vlans(args["network"])
    raise ValueError("Unknown tool: {}".format(name))


class Session:
    """State of one stdio connection: the MCP lifecycle requires initialize before anything else."""

    def __init__(self, org):
        self.org = org
        self.initialized = False


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(text):
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _validate_arguments(name, arguments):
    """Check tool arguments against the tool's inputSchema. Returns an error text, or None if valid."""
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return "Arguments must be a JSON object."
    schema = TOOL_SCHEMAS[name]
    for required in schema.get("required", []):
        if required not in arguments:
            return "Missing required argument: {}".format(required)
    for key, value in arguments.items():
        spec = schema["properties"].get(key)
        if spec is None:
            return "Unknown argument for {}: {}".format(name, key)
        if not isinstance(value, str):
            return "Argument {} must be a string.".format(key)
        if "enum" in spec and value not in spec["enum"]:
            return "Argument {} must be one of: {}.".format(key, ", ".join(spec["enum"]))
    return None


def handle(session, message):
    """Handle one JSON-RPC message. Returns the response dict, or None for notifications."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" \
            or not isinstance(message.get("method"), str):
        msg_id = message.get("id") if isinstance(message, dict) else None
        return _error(msg_id if isinstance(msg_id, (str, int)) else None, -32600, "Invalid Request")

    method = message["method"]
    if "id" not in message:
        if method == "notifications/initialized":
            session.initialized = True
        return None  # Notifications never get a reply.

    msg_id = message["id"]
    if isinstance(msg_id, bool) or not isinstance(msg_id, (str, int)):
        return _error(None, -32600, "Invalid Request: id must be a string or a number")

    params = message.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(msg_id, -32602, "Invalid params: params must be an object")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        session.initialized = True
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": "Demo Meraki organisation (simulated data). Use network_health_summary first, "
                            "then the specific tools to dig into a finding.",
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if not session.initialized:
        return _error(msg_id, -32002, "Server not initialized: send initialize first")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        if name not in TOOL_NAMES:
            return _error(msg_id, -32602, "Unknown tool: {}".format(name))
        arguments = params.get("arguments") or {}
        problem = _validate_arguments(name, arguments)
        if problem:
            return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_error(problem)}
        try:
            data = call_tool(session.org, name, arguments)
        except NetworkNotFound as error:
            return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_error(str(error))}
        text = json.dumps(data, indent=2)
        return {"jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": text}], "isError": False}}
    return _error(msg_id, -32601, "Method not found: {}".format(method))


def serve(stdin, stdout, org=None):
    session = Session(org or DemoOrg())
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = _error(None, -32700, "Parse error")
        else:
            try:
                reply = handle(session, message)
            except Exception as error:  # Never let one bad request end the session.
                traceback.print_exc(file=sys.stderr)
                msg_id = message.get("id") if isinstance(message, dict) else None
                reply = _error(msg_id if isinstance(msg_id, (str, int)) else None, -32603,
                               "Internal error: {}".format(type(error).__name__))
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main():
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    serve(stdin, stdout)


if __name__ == "__main__":
    main()
