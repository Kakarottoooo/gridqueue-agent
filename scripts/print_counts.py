from __future__ import annotations

from app.db import table_counts


def main() -> None:
    for table, count in table_counts().items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()

