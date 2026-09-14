"""Fix item balance: no item at a tier may strictly dominate another.

Many items.json entries at the same tier have identical base stats,
making one strictly dominate another. This breaks the economy:
players always pick the dominant item and ignore the rest.

Fix: for each tier, ensure every item has a UNIQUE stat combination
by giving the dominated item a compensatory stat bump that the
dominator lacks (armor for damage, damage for armor, luck for value).
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ITEMS_PATH = PROJECT_ROOT / "game" / "data" / "items.json"
NUMERIC = ("damage", "armor", "crit", "value")


def main() -> None:
    data = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    entries = data["entries"]

    by_tier: dict[int, list[dict]] = {}
    for e in entries:
        tier = int(e.get("tier", 1))
        by_tier.setdefault(tier, []).append(e)

    total_fixed = 0
    for tier, items in sorted(by_tier.items()):
        if len(items) < 2:
            continue
        total_fixed += _fix_tier(items)

    # Write the fixed data
    with open(ITEMS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"Fixed {total_fixed} dominance violations")

    # Verify by re-reading
    verify = json.loads(ITEMS_PATH.read_text(encoding="utf-8"))
    remaining = 0
    v_by_tier: dict[int, list[dict]] = {}
    for e in verify["entries"]:
        t = int(e.get("tier", 1))
        v_by_tier.setdefault(t, []).append(e)
    for tier, items in sorted(v_by_tier.items()):
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if _dominates(a, b) or _dominates(b, a):
                    remaining += 1
    print(f"Remaining dominance pairs: {remaining}")
    return remaining


def _fix_tier(items: list[dict]) -> int:
    fixed = 0
    # For each pair where A dominates B, give B a compensatory stat
    for i, a in enumerate(items):
        for j in range(len(items)):
            if i == j:
                continue
            b = items[j]
            if _dominates(a, b):
                # B is dominated by A. Give B a stat A lacks.
                a_eff = a.get("effect", {})
                b_eff = b.get("effect", {})
                # Prefer giving B armor if A has more damage
                if a_eff.get("damage", 0) > b_eff.get("armor", 0):
                    b_eff["armor"] = a_eff.get("damage", 0) + 1
                elif a_eff.get("armor", 0) > b_eff.get("damage", 0):
                    b_eff["damage"] = a_eff.get("armor", 0) + 1
                elif a_eff.get("value", 0) > b_eff.get("value", 0):
                    b_eff["value"] = a_eff.get("value", 0) + 1
                else:
                    b_eff["luck"] = b_eff.get("luck", 0) + 1
                fixed += 1
    return fixed


def _dominates(a: dict, b: dict) -> bool:
    # Combat stats live inside effect, not at top level.
    numeric = ("damage", "armor", "crit", "value")
    a_better = False
    for f in numeric:
        av = float(a.get("effect", {}).get(f, 0) or 0)
        bv = float(b.get("effect", {}).get(f, 0) or 0)
        if av < bv:
            return False
        if av > bv:
            a_better = True
    # value is top-level cost — higher value = more expensive = dominated
    av = float(a.get("value", 0) or 0)
    bv = float(b.get("value", 0) or 0)
    if av > bv:
        return False
    return a_better


if __name__ == "__main__":
    main()
