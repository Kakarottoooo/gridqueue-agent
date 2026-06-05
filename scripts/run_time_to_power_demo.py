from __future__ import annotations

from app.services.time_to_power import generate_time_to_power_brief, seed_time_to_power_fixtures


def main() -> None:
    seed_time_to_power_fixtures(reset_core=True)
    brief = generate_time_to_power_brief()
    print(brief["markdown"])
    print(f"\nWrote {brief['markdown_path']}")


if __name__ == "__main__":
    main()
