#!/usr/bin/env python3
"""Collect newly published MetaBBO papers from multiple sources, write dated briefings, and classify them."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ARXIV_API = "https://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"
OPENREVIEW_API = "https://api.openreview.net/notes"
SERPAPI_API = "https://serpapi.com/search.json"

ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def req_json(url: str, timeout: int = 30, retries: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "MetaBBO-Frontier/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read().decode("utf-8", errors="replace")
            return json.loads(data)
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if i < retries - 1:
                time.sleep(1.0 + i)
                continue
            raise last_error
    return {}


def req_text(url: str, timeout: int = 30, retries: int = 3) -> str:
    last_error: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "MetaBBO-Frontier/1.0",
                    "Accept": "application/atom+xml,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if i < retries - 1:
                time.sleep(1.0 + i)
                continue
            raise last_error
    return ""


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title(title: str) -> str:
    return normalize_ws((title or "").lower())


def parse_date_ymd(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def parse_any_date(value: str) -> dt.date | None:
    value = normalize_ws(value)
    if not value:
        return None
    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]:
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    m = re.match(r"^(\d{4})-(\d{2})", value)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), 1)
    return None


def first_year(text: str) -> str:
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    return m.group(0) if m else ""


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def match_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def infer_tags(title: str, abstract: str) -> dict[str, Any]:
    text = f"{title} {abstract}".lower()

    meta_tasks: list[str] = []
    if match_any(text, ["algorithm selection", "selector", "portfolio"]):
        meta_tasks.append("AS")
    if match_any(text, ["algorithm configuration", "parameter control", "adaptive operator", "hyperparameter"]):
        meta_tasks.append("AC")
    if match_any(text, ["learned optimizer", "optimizer policy", "trajectory", "update rule", "population update"]):
        meta_tasks.append("SM")
    if match_any(text, ["algorithm generation", "generate optimizer", "symbolic optimizer", "program synthesis", "code generation"]):
        meta_tasks.append("AG")
    if not meta_tasks:
        meta_tasks.append("Other")

    paradigms: list[str] = []
    if match_any(text, ["reinforcement learning", "deep q", "policy gradient", "ppo", "actor-critic"]):
        paradigms.append("RL")
    if match_any(text, ["supervised", "imitation", "behavior cloning", "regression"]):
        paradigms.append("SL")
    if match_any(text, ["neuroevolution", "evolution strategies", "cma-es"]):
        paradigms.append("NE")
    if match_any(text, ["in-context", "large language model", "llm", "prompt optimization"]):
        paradigms.append("ICL")
    if not paradigms:
        paradigms.append("Other")

    if match_any(text, ["multi-objective", "many-objective", "pareto"]):
        problem_type = "MOOP"
    elif match_any(text, ["constrained multiobjective", "cmop", "constraint violation"]):
        problem_type = "CMOP"
    elif match_any(text, ["multimodal optimization", "multiple optima"]):
        problem_type = "MMOP"
    elif match_any(text, ["large-scale optimization", "high-dimensional"]):
        problem_type = "LSOP"
    elif match_any(text, ["combinatorial", "tsp", "routing", "scheduling", "qubo"]):
        problem_type = "COP"
    elif match_any(text, ["single-objective", "continuous optimization", "global optimization", "black-box optimization"]):
        problem_type = "SOP"
    else:
        problem_type = "Other"

    return {
        "meta_tasks": meta_tasks,
        "learning_paradigms": paradigms,
        "problem_type": problem_type,
    }


def is_relevant_candidate(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    must = [
        "black-box",
        "black box",
        "learning to optimize",
        "learned optimizer",
        "algorithm selection",
        "algorithm configuration",
        "automated algorithm design",
        "evolutionary",
        "metaheuristic",
        "differential evolution",
        "particle swarm",
        "cma-es",
    ]
    if not any(k in text for k in must):
        return False

    core = ["optimization", "optimizer", "evolution", "algorithm"]
    return sum(1 for k in core if k in text) >= 2


def fetch_arxiv(queries: list[str], since: dt.date, until: dt.date, max_per_query: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for q in queries:
        params = {
            "search_query": q,
            "start": 0,
            "max_results": max_per_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
        try:
            text = req_text(url)
        except Exception:
            continue
        root = ET.fromstring(text)
        for entry in root.findall("atom:entry", ARXIV_NS):
            title = normalize_ws(entry.findtext("atom:title", default="", namespaces=ARXIV_NS))
            abstract = normalize_ws(entry.findtext("atom:summary", default="", namespaces=ARXIV_NS))
            published = normalize_ws(entry.findtext("atom:published", default="", namespaces=ARXIV_NS))
            date = parse_any_date(published)
            if date is None or not (since <= date <= until):
                continue
            link = ""
            for lk in entry.findall("atom:link", ARXIV_NS):
                if lk.attrib.get("rel", "") == "alternate":
                    link = lk.attrib.get("href", "")
                    break
            if not link:
                arxiv_id = normalize_ws(entry.findtext("atom:id", default="", namespaces=ARXIV_NS)).rsplit("/", 1)[-1]
                link = f"https://arxiv.org/abs/{arxiv_id}"

            items.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "url": link,
                    "date": str(date),
                    "year": str(date.year),
                    "venue": "arXiv",
                    "source": "arxiv",
                    "query": q,
                }
            )
    return items


def fetch_crossref(queries: list[str], since: dt.date, until: dt.date, max_per_query: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    since_s = since.strftime("%Y-%m-%d")
    until_s = until.strftime("%Y-%m-%d")

    for q in queries:
        params = {
            "query.bibliographic": q,
            "filter": f"from-pub-date:{since_s},until-pub-date:{until_s}",
            "rows": min(max_per_query, 100),
            "sort": "published",
            "order": "desc",
        }
        url = f"{CROSSREF_API}?{urllib.parse.urlencode(params)}"
        try:
            data = req_json(url)
        except Exception:
            continue

        for w in data.get("message", {}).get("items", []):
            title = normalize_ws((w.get("title") or [""])[0])
            if not title:
                continue
            abstract = normalize_ws(re.sub(r"<[^>]+>", " ", w.get("abstract", "") or ""))
            doi = normalize_ws(w.get("DOI", ""))
            link = f"https://doi.org/{doi}" if doi else normalize_ws((w.get("URL") or ""))

            venue = normalize_ws((w.get("container-title") or [""])[0]) or "Journal"
            year = ""
            parts = (w.get("published-print") or w.get("published-online") or {}).get("date-parts", [])
            if parts and parts[0]:
                year = str(parts[0][0])
                mm = int(parts[0][1]) if len(parts[0]) > 1 else 1
                dd = int(parts[0][2]) if len(parts[0]) > 2 else 1
                date = dt.date(int(year), mm, dd)
            else:
                date = None
                y = first_year(normalize_ws(json.dumps(w, ensure_ascii=False)))
                year = y
            if date is None:
                if year:
                    # keep year-only items if in range
                    if not (since.year <= int(year) <= until.year):
                        continue
                    dtext = f"{year}-01-01"
                else:
                    continue
            else:
                if not (since <= date <= until):
                    continue
                dtext = str(date)

            items.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "url": link,
                    "date": dtext,
                    "year": year or dtext[:4],
                    "venue": venue,
                    "source": "journal",
                    "query": q,
                }
            )
    return items


def fetch_openreview(queries: list[str], since: dt.date, until: dt.date, max_per_query: int) -> list[dict[str, Any]]:
    # Public endpoint may return 403 in some environments. Keep this source best-effort.
    items: list[dict[str, Any]] = []
    for q in queries:
        params = {
            "query": q,
            "limit": max_per_query,
            "offset": 0,
        }
        url = f"{OPENREVIEW_API}?{urllib.parse.urlencode(params)}"
        try:
            data = req_json(url)
        except Exception:
            continue
        for note in data.get("notes", []):
            content = note.get("content", {})
            title = normalize_ws(content.get("title", ""))
            abstract = normalize_ws(content.get("abstract", ""))
            if not title:
                continue
            tm = note.get("tcdate") or note.get("cdate")
            if not tm:
                continue
            date = dt.datetime.utcfromtimestamp(int(tm) / 1000).date()
            if not (since <= date <= until):
                continue
            forum = note.get("forum") or note.get("id") or ""
            link = f"https://openreview.net/forum?id={forum}" if forum else "https://openreview.net"
            venue = normalize_ws(content.get("venue", "")) or "OpenReview"
            items.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "url": link,
                    "date": str(date),
                    "year": str(date.year),
                    "venue": venue,
                    "source": "openreview",
                    "query": q,
                }
            )
    return items


def fetch_google_scholar_serpapi(queries: list[str], since: dt.date, until: dt.date, max_per_query: int) -> list[dict[str, Any]]:
    key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not key:
        return []

    items: list[dict[str, Any]] = []
    for q in queries:
        params = {
            "engine": "google_scholar",
            "q": q,
            "api_key": key,
            "num": min(max_per_query, 20),
            "as_ylo": since.year,
            "as_yhi": until.year,
        }
        url = f"{SERPAPI_API}?{urllib.parse.urlencode(params)}"
        try:
            data = req_json(url)
        except Exception:
            continue
        for r in data.get("organic_results", []):
            title = normalize_ws(r.get("title", ""))
            if not title:
                continue
            abstract = normalize_ws(r.get("snippet", ""))
            link = normalize_ws(r.get("link", ""))
            pub_sum = normalize_ws((r.get("publication_info") or {}).get("summary", ""))
            year = first_year(pub_sum) or str(until.year)
            date = f"{year}-01-01"
            venue = pub_sum or "Google Scholar"
            items.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "url": link,
                    "date": date,
                    "year": year,
                    "venue": venue,
                    "source": "google_scholar",
                    "query": q,
                }
            )
    return items


def load_existing_keys(main_library_csv: Path, local_csv: Path) -> tuple[set[str], set[str]]:
    title_keys: set[str] = set()
    link_keys: set[str] = set()

    def consume(path: Path, title_cols: list[str], link_cols: list[str]) -> None:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for c in title_cols:
                    v = normalize_title(row.get(c, ""))
                    if v:
                        title_keys.add(v)
                for c in link_cols:
                    v = normalize_ws(row.get(c, ""))
                    if v and v != "-":
                        link_keys.add(v)

    consume(main_library_csv, ["item", "paper", "title"], ["paper", "url", "code_resource"])
    consume(local_csv, ["title"], ["url"])
    return title_keys, link_keys


def choose_primary(meta_tasks: list[str], paradigms: list[str]) -> tuple[str, str]:
    task = next((t for t in ["AS", "AC", "SM", "AG"] if t in meta_tasks), "Other")
    paradigm = next((p for p in ["RL", "SL", "NE", "ICL"] if p in paradigms), "Other")
    return task, paradigm


def short_intro(abstract: str, limit: int = 220) -> str:
    if not abstract:
        return "未提供摘要，建议人工补充方法与实验要点。"
    text = normalize_ws(re.sub(r"<[^>]+>", " ", abstract))
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def ensure_local_csv(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "date",
                "title",
                "source",
                "venue",
                "year",
                "url",
                "task",
                "paradigm",
                "problem_type",
                "tags",
                "briefing_date",
                "intro",
            ],
        )
        writer.writeheader()


def append_local_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_local_csv(path)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "date",
                "title",
                "source",
                "venue",
                "year",
                "url",
                "task",
                "paradigm",
                "problem_type",
                "tags",
                "briefing_date",
                "intro",
            ],
        )
        for r in rows:
            writer.writerow(r)


def read_local_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def render_classified(local_rows: list[dict[str, str]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    by_paradigm: dict[str, list[dict[str, str]]] = {"RL": [], "SL": [], "NE": [], "ICL": [], "Other": []}
    for r in local_rows:
        by_paradigm.setdefault(r.get("paradigm", "Other"), []).append(r)

    for paradigm, rows in by_paradigm.items():
        task_groups: dict[str, list[dict[str, str]]] = {"AS": [], "AC": [], "SM": [], "AG": [], "Other": []}
        for r in rows:
            task_groups.setdefault(r.get("task", "Other"), []).append(r)

        lines = [f"# Incremental Papers via {paradigm}", ""]
        for task in ["AS", "AC", "SM", "AG", "Other"]:
            block = task_groups.get(task, [])
            if not block:
                continue
            lines.extend([f"## {task}", ""])
            lines.append("|Title|Source|Date|Problem|Link|")
            lines.append("|---|---|---|---|---|")
            for r in sorted(block, key=lambda x: x.get("date", ""), reverse=True):
                lines.append(
                    f"|{r.get('title','-')}|{r.get('source','-')}|{r.get('date','-')}|{r.get('problem_type','Other')}|[Link]({r.get('url','')})|"
                )
            lines.append("")

        fname = {
            "RL": "rl.md",
            "SL": "sl.md",
            "NE": "ne.md",
            "ICL": "icl.md",
            "Other": "other.md",
        }[paradigm]
        (out_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_briefing(new_rows: list[dict[str, Any]], out_md: Path, since: dt.date, until: dt.date) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# MetaBBO Weekly Briefing ({until})",
        "",
        f"检索区间: {since} ~ {until}",
        f"新增论文数: {len(new_rows)}",
        "",
    ]

    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in new_rows:
        by_source.setdefault(r["source"], []).append(r)

    for source in ["arxiv", "openreview", "journal", "google_scholar"]:
        rows = by_source.get(source, [])
        if not rows:
            continue
        lines.extend([f"## Source: {source}", ""])
        for i, r in enumerate(sorted(rows, key=lambda x: x.get("date", ""), reverse=True), start=1):
            lines.append(f"### {i}. {r['title']}")
            lines.append("")
            lines.append(f"- 日期: {r.get('date','-')} | 场景: {r.get('venue','-')}")
            lines.append(f"- 分类: `{r.get('paradigm','Other')}` / `{r.get('task','Other')}` / `{r.get('problem_type','Other')}`")
            lines.append(f"- 链接: {r.get('url','-')}")
            lines.append(f"- 简介: {r.get('intro','')}")
            lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")


def update_briefing_index(briefings_root: Path) -> None:
    entries = []
    for p in sorted(briefings_root.glob("*/briefing.md"), reverse=True):
        day = p.parent.name
        count = 0
        text = p.read_text(encoding="utf-8")
        m = re.search(r"新增论文数:\s*(\d+)", text)
        if m:
            count = int(m.group(1))
        rel = p.relative_to(briefings_root)
        entries.append((day, count, rel.as_posix()))

    lines = ["# Briefings Index", "", "|Date|New Papers|File|", "|---|---:|---|"]
    for d, c, rel in entries:
        lines.append(f"|{d}|{c}|[{rel}]({rel})|")
    lines.append("")
    (briefings_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect new MetaBBO papers, generate dated briefing, and classify updates.")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--since", default="", help="Start date YYYY-MM-DD; default from state file or 7 days ago")
    parser.add_argument("--until", default="", help="End date YYYY-MM-DD; default today")
    parser.add_argument("--max-per-query", type=int, default=30, help="Max records per query per source")
    parser.add_argument(
        "--query-file",
        default=".claude/skills/metabbo-research-tracker/references/source-queries.json",
        help="Path to source query json",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    state_file = repo_root / ".claude/skills/metabbo-research-tracker/references/last_run.json"

    today = dt.date.today()
    until = parse_date_ymd(args.until) if args.until else today
    if args.since:
        since = parse_date_ymd(args.since)
    else:
        state = load_json(state_file, {})
        last = state.get("last_until", "")
        since = parse_date_ymd(last) + dt.timedelta(days=1) if last else (until - dt.timedelta(days=7))

    if since > until:
        raise SystemExit("invalid range: since > until")

    query_file = repo_root / args.query_file
    qs = load_json(query_file, {})
    arxiv_queries = qs.get("arxiv", [])
    crossref_queries = qs.get("crossref", [])
    openreview_queries = qs.get("openreview", [])
    scholar_queries = qs.get("google_scholar", [])

    arxiv_items = fetch_arxiv(arxiv_queries, since, until, args.max_per_query)
    openreview_items = fetch_openreview(openreview_queries, since, until, args.max_per_query)
    crossref_items = fetch_crossref(crossref_queries, since, until, args.max_per_query)
    scholar_items = fetch_google_scholar_serpapi(scholar_queries, since, until, args.max_per_query)

    merged = arxiv_items + openreview_items + crossref_items + scholar_items

    local_csv = repo_root / "papers/updates/local_papers.csv"
    main_csv = repo_root / "papers/library.csv"
    existing_titles, existing_links = load_existing_keys(main_csv, local_csv)

    dedup_map: dict[str, dict[str, Any]] = {}
    for it in merged:
        title_key = normalize_title(it.get("title", ""))
        link_key = normalize_ws(it.get("url", ""))
        if not title_key:
            continue
        if title_key in existing_titles or (link_key and link_key in existing_links):
            continue
        if not is_relevant_candidate(it.get("title", ""), it.get("abstract", "")):
            continue
        key = title_key
        if key in dedup_map:
            continue

        tags = infer_tags(it.get("title", ""), it.get("abstract", ""))
        task, paradigm = choose_primary(tags["meta_tasks"], tags["learning_paradigms"])
        intro = short_intro(it.get("abstract", ""))
        item = {
            **it,
            "task": task,
            "paradigm": paradigm,
            "problem_type": tags["problem_type"],
            "tags": ",".join(tags["meta_tasks"] + tags["learning_paradigms"]),
            "intro": intro,
        }
        dedup_map[key] = item

    new_rows = sorted(dedup_map.values(), key=lambda x: x.get("date", ""), reverse=True)

    # Write dated briefing artifacts
    day_dir = repo_root / "papers/briefings" / str(until)
    day_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(day_dir / "new-papers.jsonl", new_rows)
    render_briefing(new_rows, day_dir / "briefing.md", since, until)
    update_briefing_index(repo_root / "papers/briefings")

    # Append to local update csv
    briefing_date = str(until)
    append_rows = []
    for idx, r in enumerate(new_rows, start=1):
        rid = f"upd-{briefing_date}-{idx:03d}"
        append_rows.append(
            {
                "id": rid,
                "date": r.get("date", ""),
                "title": r.get("title", ""),
                "source": r.get("source", ""),
                "venue": r.get("venue", ""),
                "year": r.get("year", ""),
                "url": r.get("url", ""),
                "task": r.get("task", "Other"),
                "paradigm": r.get("paradigm", "Other"),
                "problem_type": r.get("problem_type", "Other"),
                "tags": r.get("tags", ""),
                "briefing_date": briefing_date,
                "intro": r.get("intro", ""),
            }
        )

    if append_rows:
        append_local_csv(local_csv, append_rows)

    # Re-render classified local update views
    local_rows = read_local_csv(local_csv)
    render_classified(local_rows, repo_root / "papers/updates/classified")

    save_json(
        state_file,
        {
            "last_since": str(since),
            "last_until": str(until),
            "last_new_count": len(new_rows),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )

    print(
        "range=%s..%s arxiv=%d openreview=%d journal=%d scholar=%d new=%d"
        % (since, until, len(arxiv_items), len(openreview_items), len(crossref_items), len(scholar_items), len(new_rows))
    )
    print(f"briefing={day_dir / 'briefing.md'}")
    print(f"local_csv={local_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
