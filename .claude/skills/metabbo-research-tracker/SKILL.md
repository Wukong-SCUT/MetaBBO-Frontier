---
name: metabbo-research-tracker
description: Track newly published MetaBBO research and maintain dated briefings plus classified update lists. Use when the user asks to scan papers since the last update, gather papers from arXiv/OpenReview/journals (and optional Google Scholar API), write per-paper weekly briefs, and classify new papers into AS/AC/SM/AG and RL/SL/NE/ICL.
---

# MetaBBO Research Tracker

## Quick Workflow

1. Run multi-source incremental scan (`since` -> `until`).
2. Filter and classify papers into `AS/AC/SM/AG` + `RL/SL/NE/ICL`.
3. Generate a dated briefing file under `papers/briefings/YYYY-MM-DD/`.
4. Update local classified views under `papers/updates/classified/`.

## Command (Incremental)

Run from repository root:

```bash
python3 .claude/skills/metabbo-research-tracker/scripts/collect_metabbo_updates.py \
  --repo-root . \
  --max-per-query 30
```

Optional explicit date range:

```bash
python3 .claude/skills/metabbo-research-tracker/scripts/collect_metabbo_updates.py \
  --repo-root . \
  --since 2026-04-01 \
  --until 2026-04-15 \
  --max-per-query 40
```

## Output Files

- Dated report: `papers/briefings/YYYY-MM-DD/briefing.md`
- Raw records: `papers/briefings/YYYY-MM-DD/new-papers.jsonl`
- Briefing index: `papers/briefings/README.md`
- Local update DB: `papers/updates/local_papers.csv`
- Classified incremental views:
  - `papers/updates/classified/rl.md`
  - `papers/updates/classified/sl.md`
  - `papers/updates/classified/ne.md`
  - `papers/updates/classified/icl.md`
  - `papers/updates/classified/other.md`

## Sources

- arXiv (direct API)
- OpenReview (best-effort; some environments may block public API)
- Journal index (Crossref API)
- Google Scholar (optional via `SERPAPI_API_KEY`)

## Notes on Google Scholar

Direct Google Scholar scraping is unstable and often blocked. This skill uses Google Scholar only when `SERPAPI_API_KEY` is provided.

## Query Configuration

Edit source query sets in:

- `references/source-queries.json`

## Classification Standard

Use `references/tagging.md`.

- Meta task: `AS`, `AC`, `SM`, `AG`
- Learning paradigm: `RL`, `SL`, `NE`, `ICL`
- Problem type: `SOP`, `MOOP`, `CMOP`, `MMOP`, `LSOP`, `COP`, `Other`

## References

- `references/source-queries.json`
- `references/tagging.md`
- `scripts/collect_metabbo_updates.py`
