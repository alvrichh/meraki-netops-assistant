"""Print the health summary in the terminal, without Claude.

    python3 -m netops.cli            # every network
    python3 -m netops.cli dublin     # one network
"""

import sys

from netops.data import DemoOrg, NetworkNotFound

ICONS = {"healthy": "OK  ", "degraded": "WARN", "down": "DOWN"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    network = argv[0] if argv else None
    try:
        summaries = DemoOrg().health_summary(network)
    except NetworkNotFound as error:
        print(error, file=sys.stderr)
        return 1
    for summary in summaries:
        print("[{}] {}".format(ICONS[summary["status"]], summary["network"]))
        for finding in summary["findings"]:
            print("   - {:8} {}".format(finding["severity"].upper(), finding["detail"]))
            print("     next: {}".format(finding["suggestedAction"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
