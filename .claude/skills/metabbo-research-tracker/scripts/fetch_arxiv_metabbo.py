#!/usr/bin/env python3
"""Fetch latest MetaBBO-related papers from arXiv and suggest taxonomy tags."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

API_URL = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

DEFAULT_QUERIES = [
    'all:"meta black box optimization"',
    'all:"meta-black-box-optimization"',
    'all:"learning to optimize" AND all:"black-box"',
    'ti:"learned optimizer" AND all:"evolutionary"',
    'all:"algorithm selection" AND all:"black-box optimization"',
    'all:"algorithm configuration" AND all:"differential evolution"',
    'all:"adaptive operator selection" AND all:"evolutionary algorithm"',
    'all:"LLM" AND all:"optimization" AND all:"evolutionary"',
    'all:"in-context optimization" AND all:"black-box"',
]


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def load_queries(path: str | None) -> list[str]:
    if path is None:
        return DEFAULT_QUERIES

    queries: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            tick_match = re.match(r"\s*-\s*`(.+?)`\s*$", line)
            if tick_match:
                queries.append(tick_match.group(1).strip())

    return queries if queries else DEFAULT_QUERIES


def parse_dt(value: str) -> dt.datetime:
    # arXiv format: 2026-03-10T03:55:32Z
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def fetch_entries(query: str, max_results: int, timeout: int = 30) -> list[dict[str, Any]]:
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "MetaBBO-Frontier/1.0"})

    last_error: Exception | None = None
    content = b""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read()
            break
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
                continue
            raise last_error

    root = ET.fromstring(content)
    results: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", NS):
        entry_id = normalize_ws(entry.findtext("atom:id", default="", namespaces=NS))
        arxiv_id_with_ver = entry_id.rsplit("/", 1)[-1] if entry_id else ""
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id_with_ver)

        title = normalize_ws(entry.findtext("atom:title", default="", namespaces=NS))
        summary = normalize_ws(entry.findtext("atom:summary", default="", namespaces=NS))
        published = normalize_ws(entry.findtext("atom:published", default="", namespaces=NS))
        updated = normalize_ws(entry.findtext("atom:updated", default="", namespaces=NS))

        authors = [
            normalize_ws(author.findtext("atom:name", default="", namespaces=NS))
            for author in entry.findall("atom:author", NS)
        ]
        authors = [a for a in authors if a]

        categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", NS)]
        categories = [c for c in categories if c]

        primary_cat = ""
        primary = entry.find("arxiv:primary_category", NS)
        if primary is not None:
            primary_cat = normalize_ws(primary.attrib.get("term", ""))

        link = ""
        for candidate in entry.findall("atom:link", NS):
            rel = candidate.attrib.get("rel", "")
            if rel == "alternate":
                link = candidate.attrib.get("href", "")
                break
        if not link and arxiv_id:
            link = f"https://arxiv.org/abs/{arxiv_id}"

        if not arxiv_id or not title:
            continue

        results.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "published": published,
                "updated": updated,
                "authors": authors,
                "categories": categories,
                "primary_category": primary_cat,
                "url": link,
            }
        )

    return results


def match_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def infer_tags(title: str, summary: str) -> dict[str, Any]:
    text = f"{title} {summary}".lower()

    meta_tasks: list[str] = []
    if match_any(text, ["algorithm selection", "portfolio", "selector"]):
        meta_tasks.append("AS")
    if match_any(text, ["algorithm configuration", "parameter control", "adaptive operator", "hyperparameter", "configuration"]):
        meta_tasks.append("AC")
    if match_any(text, ["learned optimizer", "optimizer policy", "trajectory", "update rule", "population update"]):
        meta_tasks.append("SM")
    if match_any(text, ["algorithm generation", "generate optimizer", "symbolic optimizer", "program synthesis", "llm-generated", "code generation"]):
        meta_tasks.append("AG")
    if not meta_tasks:
        meta_tasks.append("OtherTask")

    paradigms: list[str] = []
    if match_any(text, ["reinforcement learning", "deep q", "policy gradient", "ppo", "actor-critic"]):
        paradigms.append("RL")
    if match_any(text, ["supervised", "imitation", "behavior cloning", "regression"]):
        paradigms.append("SL")
    if match_any(text, ["neuroevolution", "evolution strategies", "es-"]):
        paradigms.append("NE")
    if match_any(text, ["in-context", "large language model", "llm", "prompt optimization"]):
        paradigms.append("ICL")
    if not paradigms:
        paradigms.append("OtherParadigm")

    if match_any(text, ["multi-objective", "many-objective", "pareto"]):
        problem_type = "MOOP"
    elif match_any(text, ["constrained multiobjective", "cmop", "constraint violation"]):
        problem_type = "CMOP"
    elif match_any(text, ["multimodal optimization", "multiple optima"]):
        problem_type = "MMOP"
    elif match_any(text, ["large-scale optimization", "high-dimensional", "thousands of variables"]):
        problem_type = "LSOP"
    elif match_any(text, ["combinatorial", "tsp", "routing", "scheduling"]):
        problem_type = "COP"
    elif match_any(text, ["single-objective", "continuous optimization", "global optimization"]):
        problem_type = "SOP"
    else:
        problem_type = "Other"

    if match_any(text, ["meta-black-box", "meta black box", "learning to optimize", "learned optimizer"]):
        priority = "P1"
    elif any(task in {"AS", "AC", "SM", "AG"} for task in meta_tasks):
        priority = "P2"
    else:
        priority = "P3"

    tags = [priority, problem_type] + meta_tasks + paradigms
    tags = sorted(set(tags), key=tags.index)

    return {
        "meta_tasks": meta_tasks,
        "learning_paradigms": paradigms,
        "problem_type": problem_type,
        "priority": priority,
        "suggested_tags": tags,
    }


def is_relevant_candidate(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()

    anchor_terms = [
        "meta",
        "black-box",
        "black box",
        "algorithm selection",
        "algorithm configuration",
        "operator selection",
        "hyperparameter control",
        "learned optimizer",
        "learning to optimize",
        "automated algorithm design",
        "evolutionary algorithm",
        "differential evolution",
        "swarm intelligence",
        "cma-es",
    ]
    if not any(term in text for term in anchor_terms):
        return False

    direct_terms = [
        "meta-black-box",
        "meta black box",
        "learning to optimize",
        "learned optimizer",
        "meta-level",
    ]
    if any(term in text for term in direct_terms):
        return True

    bbo_terms = [
        "black-box optimization",
        "derivative-free",
        "global optimization",
        "combinatorial optimization",
    ]
    design_terms = [
        "algorithm selection",
        "algorithm configuration",
        "operator selection",
        "hyperparameter control",
        "automated algorithm design",
    ]
    evo_terms = [
        "evolutionary algorithm",
        "differential evolution",
        "particle swarm",
        "cma-es",
        "neuroevolution",
        "swarm intelligence",
    ]

    score = 0
    if any(term in text for term in bbo_terms):
        score += 1
    if any(term in text for term in design_terms):
        score += 1
    if any(term in text for term in evo_terms):
        score += 1
    return score >= 2


def write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_markdown(path: str, rows: list[dict[str, Any]], days: int, queries: list[str]) -> None:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Latest MetaBBO Candidates from arXiv",
        "",
        f"Generated: {now}",
        f"Time window: last {days} days",
        f"Query count: {len(queries)}",
        f"Candidate count: {len(rows)}",
        "",
        "## Candidates",
        "",
    ]

    for item in rows:
        authors = ", ".join(item.get("authors", [])[:4])
        if len(item.get("authors", [])) > 4:
            authors += ", et al."
        tags = ", ".join(item.get("suggested_tags", []))
        lines.extend(
            [
                f"- **{item['title']}**",
                f"  - arXiv: {item['arxiv_id']} | Published: {item['published'][:10]}",
                f"  - Link: {item['url']}",
                f"  - Authors: {authors}",
                f"  - Suggested tags: {tags}",
            ]
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch latest MetaBBO-related papers from arXiv.")
    parser.add_argument("--query-file", default=None, help="Markdown file containing query lines formatted as '- `query`'.")
    parser.add_argument("--days", type=int, default=30, help="Only keep papers published in the last N days.")
    parser.add_argument("--max-results", type=int, default=120, help="Approximate total number of candidates to fetch.")
    parser.add_argument(
        "--strict-filter",
        type=int,
        default=1,
        help="Use lightweight relevance filter (1=on, 0=off).",
    )
    parser.add_argument("--output-jsonl", required=True, help="Path to output JSONL.")
    parser.add_argument("--output-markdown", default=None, help="Optional path to output Markdown summary.")
    args = parser.parse_args()

    if args.days <= 0:
        print("--days must be positive", file=sys.stderr)
        return 2
    if args.max_results <= 0:
        print("--max-results must be positive", file=sys.stderr)
        return 2

    queries = load_queries(args.query_file)
    per_query = max(8, min(50, math.ceil(args.max_results / len(queries))))

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    by_id: dict[str, dict[str, Any]] = {}

    for query in queries:
        try:
            entries = fetch_entries(query, per_query)
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] query failed: {query} | {exc}", file=sys.stderr)
            continue

        for entry in entries:
            published_dt = parse_dt(entry["published"])
            if published_dt < cutoff:
                continue
            if args.strict_filter and not is_relevant_candidate(entry["title"], entry["summary"]):
                continue

            current = by_id.get(entry["arxiv_id"])
            if current is None:
                tags = infer_tags(entry["title"], entry["summary"])
                row = {
                    **entry,
                    **tags,
                    "matched_queries": [query],
                }
                by_id[entry["arxiv_id"]] = row
            else:
                current.setdefault("matched_queries", []).append(query)

    rows = list(by_id.values())
    rows.sort(key=lambda x: x["published"], reverse=True)

    write_jsonl(args.output_jsonl, rows)
    if args.output_markdown:
        write_markdown(args.output_markdown, rows, args.days, queries)

    print(f"queries={len(queries)} candidates={len(rows)} output={args.output_jsonl}")
    if args.output_markdown:
        print(f"markdown={args.output_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
