"""Second-process reader for the save round-trip (tools/qa/acceptance.py).

Loads save.json, prints what it read, optionally buys upgrades, then writes back.
    python tools/qa/reader.py --buy
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from game.systems import save as save_sys  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools.qa.reader")
    parser.add_argument("--buy", action="store_true", help="purchase upgrades with the essence")
    parser.add_argument("--path", default=None)
    args = parser.parse_args(argv)

    profile, notes = save_sys.load_profile(args.path)
    print("reader: notes=%s" % notes)
    print("reader: essence=%d meta=%s" % (profile["essence"], profile["meta"]))
    print("reader: levels=%s stats=%s run=%s"
          % (profile["levels"], profile["stats"], profile["run"]))
    print("reader: meta totals=%s" % save_sys.meta_stat_totals(profile))

    if args.buy:
        bought = []
        for uid in ("vitality", "might"):
            while save_sys.purchase(profile, uid):
                bought.append(uid)
        save_sys.save_profile(profile, args.path)
        print("reader: bought=%s remaining essence=%d meta=%s"
              % (bought, profile["essence"], profile["meta"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
