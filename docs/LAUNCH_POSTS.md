# Launch Posts

Use these drafts when publishing the first GridQueue Agent public demo. Keep the discovery first, then point readers to
the demo, GitHub repo, and evidence files.

## Links

- Web demo: https://gridqueue-web.onrender.com
- GitHub: https://github.com/Kakarottoooo/gridqueue-agent
- API docs: https://gridqueue-api.onrender.com/docs
- Real validation report: https://github.com/Kakarottoooo/gridqueue-agent/blob/main/docs/REAL_DATA_VALIDATION.md
- ERCOT digest: https://github.com/Kakarottoooo/gridqueue-agent/blob/main/reports/real_data/ercot/real_monthly_digest_2026_04_to_2026_05.md
- Entity-resolution audit: https://github.com/Kakarottoooo/gridqueue-agent/blob/main/reports/real_data/entity_resolution_audit/ercot_matches_2026_04_to_2026_05.csv
- LBNL reproduction: https://github.com/Kakarottoooo/gridqueue-agent/blob/main/reports/real_data/lbnl/lbnl_reproduction.md

## X Thread

FERC is expected to act this month on large-load interconnection rules.

The obvious question is: "Will data centers connect faster?"

The better question is: "Faster into what queue?"

I compared two real ERCOT GIS snapshots, April -> May 2026.

Result: 210 material queue events in one month:

- 77 target COD delays
- 26 new projects
- 12 withdrawn
- 12 completed
- 57 projects missing from the later snapshot

Every number is traceable to public ERCOT files, with file hashes and row counts.

The lesson: curtailable load may help large loads move faster through studies. But it does not make the surrounding
generation/storage queue stable.

I built GridQueue Agent to make this kind of public queue intelligence reproducible:

- ingest public queue files
- normalize messy project records
- resolve entities across monthly snapshots
- detect queue changes
- generate source-traceable briefs
- audit entity-resolution decisions

Try the public demo:
https://gridqueue-web.onrender.com

GitHub:
https://github.com/Kakarottoooo/gridqueue-agent

Evidence:
https://github.com/Kakarottoooo/gridqueue-agent/blob/main/docs/REAL_DATA_VALIDATION.md

Important caveat: this ERCOT slice is generation/storage GIS data, not a complete data-center or large-load queue. I am
using it as a stress test for queue stability, not as a claim that FERC directly changes ERCOT rules.

If you want a version for your ISO, county, or project watchlist, reply/DM or email ziweiguo666@gmail.com.

## LinkedIn Post

FERC is expected to act by the end of June on RM26-4, the large-load interconnection docket aimed at data centers and
other >20 MW loads.

Most discussion is focused on whether large loads can move faster through interconnection studies, especially if they
agree to be flexible or curtailable.

I think the more practical question is slightly different:

If a large load gets a faster path, what exactly is it connecting into?

To ground that question, I compared two real ERCOT GIS monthly snapshots: April 2026 and May 2026. This is not a model
output or a market forecast. It is a public-source queue diff, with file hashes, row counts, and source traces.

In one month, the ERCOT generation/storage queue showed 210 material events:

- 77 target COD delays
- 26 new projects
- 12 withdrawals
- 12 completions
- 57 projects that appeared in the April snapshot but not in the May snapshot

That does not mean FERC's rule directly applies to ERCOT. Jurisdiction matters. But ERCOT is a useful stress test for
the same commercial problem every data center developer now faces: speed to power is not just a load-interconnection
question. It is a queue-stability question.

I built GridQueue Agent to make this analysis reproducible. It ingests public queue files, normalizes messy project
records, resolves entities across monthly snapshots, detects material changes, and generates source-traceable briefs.
The real-data validation slice includes:

- two official ERCOT GIS monthly workbooks
- file hashes and row counts
- a month-over-month ERCOT queue digest
- a 2,206-row entity-resolution audit CSV
- an LBNL Queued Up workbook reproduction check with documented mismatches

Public demo:
https://gridqueue-web.onrender.com

GitHub:
https://github.com/Kakarottoooo/gridqueue-agent

Real validation report:
https://github.com/Kakarottoooo/gridqueue-agent/blob/main/docs/REAL_DATA_VALIDATION.md

The demo uses deterministic fixture data so anyone can test the workflow in a browser. The credibility layer is the
checked-in real-data evidence: source hashes, row counts, traces, audit rows, and limitations.

If you want this kind of monthly queue intelligence for a specific ISO, county, project list, or data-center power
strategy, reply here or email ziweiguo666@gmail.com.

