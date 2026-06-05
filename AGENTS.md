## Completion notification

When finishing a substantive Codex task, run the completion sound helper before sending the final response:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\Gzw19\.codex\hooks\notify-complete.ps1"
```

Use it for completed coding/debugging/review/documentation tasks and long status handoffs. Skip it for tiny chat-only
replies unless the user explicitly asks for a sound test.

## Public Project Release Playbook

For future projects, do not stop at "the repo works locally." Package the work so outsiders can understand, verify, and
try it.

1. Lead with a real finding, not the tool. Open launch copy with the surprising domain insight, then explain the system
   as the credibility layer.
2. Make the README first screen answer: what is this, why should I care, how do I try it, where is the evidence, and
   what are the limitations.
3. Ship a public demo URL when feasible. If the app has a backend, include `/health`, `/docs`, and a root route that
   points visitors to the right place.
4. Preserve source-backed evidence. Link to hashes, row counts, source traces, audit files, mismatch notes, and caveats.
5. Separate demo data from real validation. A browser demo can use fixtures; credibility should come from committed
   real-data reports and clear raw-data handling.
6. Publish with four links: the finding thread/post, the web demo, the GitHub repo, and the strongest evidence file.
7. Add a soft CTA: reply, DM, or email for a specific ISO, county, project watchlist, or customer version.
8. Track demand signals from day one: subscribers, named industry replies, DMs, screenshots, requests for a custom
   version, and any company-specific inbound.
9. Avoid unsupported claims. For GridQueue, do not describe ERCOT GIS generation/storage data as a complete large-load
   or data-center queue.

