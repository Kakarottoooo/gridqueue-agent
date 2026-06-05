from __future__ import annotations

from app.services.time_to_power import seed_time_to_power_fixtures


def main() -> None:
    result = seed_time_to_power_fixtures(reset_core=False)
    print(result)


if __name__ == "__main__":
    main()
