from __future__ import annotations

from app.services.brief_generation import generate_brief
from app.services.ingestion import run_fixture_pipeline


def main() -> None:
    run_fixture_pipeline(reset=True)
    brief = generate_brief(
        market="ERCOT",
        project_type="Battery",
        county="Reeves",
        capacity_mw=100,
        target_cod_year=2028,
        question="What public interconnection risks should I know for a data center load?",
        min_sample_n=2,
    )
    print(brief["markdown"])


if __name__ == "__main__":
    main()

