from __future__ import annotations

from app.services.flexibility import list_flexibility_rules, seed_flexibility_rules


def main() -> None:
    result = seed_flexibility_rules()
    rules = list_flexibility_rules()
    print("Seeded flexibility rules and compute-cost assumptions")
    print(result)
    print({"rules": len(rules), "jurisdictions": sorted({rule["jurisdiction"] for rule in rules})})


if __name__ == "__main__":
    main()
