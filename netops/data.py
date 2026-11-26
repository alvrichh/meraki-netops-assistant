"""Read-only queries over the demo Meraki organisation.

Every method returns plain dicts and lists shaped like Meraki Dashboard API v1
responses, so a live data source could replace this class later without
changing the MCP tools.
"""

import ipaddress
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "demo-org.json"

# Thresholds used by the health summary.
CHANNEL_UTILIZATION_ALERT = 70.0  # percent, any band
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class NetworkNotFound(ValueError):
    """Raised when a network name or id does not match exactly one network."""


class DemoOrg:
    def __init__(self, path=DATA_FILE):
        with open(path, encoding="utf-8") as handle:
            self._data = json.load(handle)

    # ---------------------------------------------------------------- lookups

    def organization(self):
        return self._data["organization"]

    def networks(self):
        return list(self._data["networks"])

    def resolve_network(self, query):
        """Find one network by id or by (part of) its name, case-insensitive."""
        text = str(query).strip().lower()
        networks = self._data["networks"]
        for network in networks:
            if network["id"].lower() == text:
                return network
        matches = [n for n in networks if text and text in n["name"].lower()]
        if len(matches) == 1:
            return matches[0]
        known = ", ".join(n["name"] for n in networks)
        if not matches:
            raise NetworkNotFound("No network matches '{}'. Known networks: {}.".format(query, known))
        names = ", ".join(n["name"] for n in matches)
        raise NetworkNotFound("'{}' matches several networks: {}. Be more specific.".format(query, names))

    def _network_ids(self, network=None):
        if network is None or str(network).strip() == "":
            return [n["id"] for n in self._data["networks"]]
        return [self.resolve_network(network)["id"]]

    # ---------------------------------------------------------------- queries

    def device_statuses(self, network=None, status=None):
        ids = set(self._network_ids(network))
        devices = [d for d in self._data["devices"] if d["networkId"] in ids]
        if status:
            devices = [d for d in devices if d["status"] == status.lower()]
        return devices

    def uplink_statuses(self, network=None):
        ids = set(self._network_ids(network))
        return [u for u in self._data["uplinkStatuses"] if u["networkId"] in ids]

    def clients(self, network):
        return list(self._data["clients"].get(self.resolve_network(network)["id"], []))

    def events(self, network, event_type=None):
        items = self._data["events"].get(self.resolve_network(network)["id"], [])
        if event_type:
            items = [e for e in items if e["type"] == event_type]
        return sorted(items, key=lambda e: e["occurredAt"], reverse=True)

    def channel_utilization(self, network):
        return list(self._data["channelUtilization"].get(self.resolve_network(network)["id"], []))

    def vlans(self, network):
        network_id = self.resolve_network(network)["id"]
        result = []
        for vlan in self._data["vlans"].get(network_id, []):
            item = dict(vlan)
            item["usableHosts"] = ipaddress.ip_network(vlan["subnet"]).num_addresses - 2
            result.append(item)
        return result

    # ---------------------------------------------------------------- health

    def health_summary(self, network=None):
        """Check each network and return findings with a suggested next action."""
        return [self._network_health(network_id) for network_id in self._network_ids(network)]

    def _network_health(self, network_id):
        network = self.resolve_network(network_id)
        findings = []
        findings += self._device_findings(network_id)
        findings += self._uplink_findings(network)
        findings += self._wireless_findings(network_id)
        findings += self._dhcp_findings(network_id)
        findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])

        if any(f["severity"] == "critical" for f in findings):
            status = "down"
        elif findings:
            status = "degraded"
        else:
            status = "healthy"
        return {"network": network["name"], "networkId": network_id, "status": status, "findings": findings}

    def _device_findings(self, network_id):
        findings = []
        for device in self.device_statuses(network_id):
            if device["status"] == "offline":
                findings.append({
                    "severity": "high",
                    "area": "device",
                    "detail": "{} ({}, {}) is offline; last reported {}.".format(
                        device["name"], device["model"], device["serial"], device["lastReportedAt"]),
                    "suggestedAction": "Check power and PoE on its switch port, then the cabling; "
                                       "if the port is up, power-cycle the device from the dashboard.",
                })
            elif device["status"] == "alerting":
                findings.append({
                    "severity": "medium",
                    "area": "device",
                    "detail": "{} ({}) is alerting.".format(device["name"], device["model"]),
                    "suggestedAction": "Open the device in the dashboard and review its active alerts.",
                })
        return findings

    def _uplink_findings(self, network):
        findings = []
        circuits = {c["interface"]: c for c in network.get("ispCircuits", [])}
        for appliance in self.uplink_statuses(network["id"]):
            uplinks = appliance["uplinks"]
            failed = [u for u in uplinks if u["status"] == "failed"]
            active = [u for u in uplinks if u["status"] == "active"]
            for uplink in failed:
                circuit = circuits.get(uplink["interface"], {})
                severity = "critical" if not active else "high"
                running_on = ", ".join(u["interface"] for u in active) or "nothing"
                findings.append({
                    "severity": severity,
                    "area": "uplink",
                    "detail": "Uplink {} is down on {}; traffic is running on {}.".format(
                        uplink["interface"], appliance["serial"], running_on),
                    "suggestedAction": "Raise a fault with {} for circuit {}, with the failure time and "
                                       "gateway {}; watch backup capacity meanwhile.".format(
                                           circuit.get("provider", "the ISP"),
                                           circuit.get("circuitId", "(unknown circuit)"),
                                           uplink["gateway"]),
                })
        return findings

    def _wireless_findings(self, network_id):
        names = {d["serial"]: d["name"] for d in self._data["devices"]}
        findings = []
        for ap in self.channel_utilization(network_id):
            for band, label in (("wifi0", "2.4 GHz"), ("wifi1", "5 GHz")):
                for sample in ap.get(band, []):
                    total = sample["utilizationTotal"]
                    if total >= CHANNEL_UTILIZATION_ALERT:
                        findings.append({
                            "severity": "medium",
                            "area": "wireless",
                            "detail": "{} has {:.1f}% channel utilisation on {} ({:.1f}% non-Wi-Fi "
                                      "interference).".format(names.get(ap["serial"], ap["serial"]), total,
                                                               label, sample["utilizationNon80211"]),
                            "suggestedAction": "Spread clients to nearby APs (check that none of them is "
                                               "offline), review channel and band steering, and look for "
                                               "interference sources.",
                        })
        return findings

    def _dhcp_findings(self, network_id):
        no_leases = [e for e in self.events(network_id, "dhcp_no_leases")]
        if not no_leases:
            return []
        latest = no_leases[0]
        vlan_id = latest.get("eventData", {}).get("vlan")
        vlan = next((v for v in self.vlans(network_id) if v["id"] == vlan_id), None)
        size = "{} ({} usable addresses)".format(vlan["subnet"], vlan["usableHosts"]) if vlan else "unknown subnet"
        return [{
            "severity": "high",
            "area": "dhcp",
            "detail": "DHCP ran out of leases {} times on VLAN {} {}; latest at {}.".format(
                len(no_leases), vlan_id, size, latest["occurredAt"]),
            "suggestedAction": "Enlarge the subnet (for example to a /24) or shorten the lease time "
                               "on that VLAN.",
        }]
