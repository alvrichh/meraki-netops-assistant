import unittest

from netops.data import DemoOrg, NetworkNotFound


class ResolveNetworkTest(unittest.TestCase):
    def setUp(self):
        self.org = DemoOrg()

    def test_by_partial_name_case_insensitive(self):
        self.assertEqual(self.org.resolve_network("dublin")["id"], "N_1001")

    def test_by_id(self):
        self.assertEqual(self.org.resolve_network("N_1003")["name"], "Barcelona")

    def test_unknown_network_lists_known_ones(self):
        with self.assertRaises(NetworkNotFound) as ctx:
            self.org.resolve_network("tokyo")
        self.assertIn("Dublin HQ", str(ctx.exception))

    def test_ambiguous_name(self):
        with self.assertRaises(NetworkNotFound):
            self.org.resolve_network("o")  # matches London and San Francisco, among others


class QueryTest(unittest.TestCase):
    def setUp(self):
        self.org = DemoOrg()

    def test_offline_devices(self):
        offline = self.org.device_statuses(status="offline")
        self.assertEqual([d["name"] for d in offline], ["DUB-AP-3F-02"])

    def test_events_newest_first_and_filtered(self):
        events = self.org.events("barcelona", "dhcp_no_leases")
        self.assertEqual(len(events), 3)
        self.assertGreater(events[0]["occurredAt"], events[-1]["occurredAt"])

    def test_vlan_usable_hosts(self):
        guest = [v for v in self.org.vlans("barcelona") if v["id"] == 30][0]
        self.assertEqual(guest["usableHosts"], 62)


class HealthSummaryTest(unittest.TestCase):
    def setUp(self):
        self.summary = {s["network"]: s for s in DemoOrg().health_summary()}

    def areas(self, network):
        return [f["area"] for f in self.summary[network]["findings"]]

    def test_dublin_offline_ap_and_busy_channel(self):
        self.assertEqual(self.summary["Dublin HQ"]["status"], "degraded")
        self.assertEqual(self.areas("Dublin HQ"), ["device", "wireless"])

    def test_london_on_backup_uplink_names_the_circuit(self):
        findings = self.summary["London"]["findings"]
        uplink = [f for f in findings if f["area"] == "uplink"][0]
        self.assertEqual(uplink["severity"], "high")
        self.assertIn("BT-LON-77310", uplink["suggestedAction"])

    def test_barcelona_dhcp_exhaustion(self):
        self.assertEqual(self.areas("Barcelona"), ["dhcp"])
        self.assertIn("62 usable", self.summary["Barcelona"]["findings"][0]["detail"])

    def test_san_francisco_healthy(self):
        self.assertEqual(self.summary["San Francisco"]["status"], "healthy")
        self.assertEqual(self.summary["San Francisco"]["findings"], [])


if __name__ == "__main__":
    unittest.main()
