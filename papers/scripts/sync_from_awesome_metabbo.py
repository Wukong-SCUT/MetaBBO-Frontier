#!/usr/bin/env python3
"""Sync paper library from MetaEvo/Awesome-MetaBBO README tables."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path
from typing import Any

SOURCE_URL = "https://raw.githubusercontent.com/MetaEvo/Awesome-MetaBBO/main/README.md"


def fetch_text(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        req = urllib.request.Request(source, headers={"User-Agent": "MetaBBO-Frontier-Sync/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")
    return Path(source).read_text(encoding="utf-8")


def parse_markdown_row(line: str) -> list[str] | None:
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_delimiter_row(cells: list[str]) -> bool:
    if not cells:
        return False
    cleaned = [c.replace(" ", "") for c in cells]
    return all(c and set(c) <= set(":-") and "-" in c for c in cleaned)


def slug(s: str) -> str:
    s = re.sub(r"\*\*|`|\[|\]|\(|\)", "", s)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:80] if s else "item"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["|" + "|".join(headers) + "|", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        rr = r + [""] * (len(headers) - len(r))
        out.append("|" + "|".join(rr[: len(headers)]) + "|")
    return "\n".join(out)


def normalize_task_from_h4(h4: str) -> str:
    if "Algorithm Selection" in h4:
        return "AS"
    if "Algorithm Configuration" in h4:
        return "AC"
    if "Solution Manipulation" in h4:
        return "SM"
    if "Algorithm Generation" in h4:
        return "AG"
    return "Other"


def parse_tables(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    h2 = ""
    h3 = ""
    h4 = ""
    entries: list[dict[str, Any]] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            h2 = line.strip()
        elif line.startswith("### "):
            h3 = line.strip()
            h4 = ""
        elif line.startswith("#### "):
            h4 = line.strip()

        row = parse_markdown_row(line)
        if row is None:
            i += 1
            continue

        # Collect table block
        block: list[list[str]] = []
        j = i
        while j < len(lines):
            rr = parse_markdown_row(lines[j])
            if rr is None:
                break
            block.append(rr)
            j += 1

        i = j
        if len(block) < 2:
            continue

        header = block[0]
        body = block[1:]
        if body and is_delimiter_row(body[0]):
            body = body[1:]

        # Skip non-paper list tables outside content sections
        if not (
            h3.startswith("### 1.1")
            or h3.startswith("### 1.2")
            or h3.startswith("### 2.1")
            or h3.startswith("### 2.2")
            or h3.startswith("### 2.3")
            or h3.startswith("### 2.4")
            or h3.startswith("### 3.1")
            or h3.startswith("### 3.2")
            or h3.startswith("### 3.3")
        ):
            continue

        for r in body:
            if not any(c.strip() for c in r):
                continue
            if len(r) < len(header):
                r = r + [""] * (len(header) - len(r))
            elif len(r) > len(header):
                r = r[: len(header) - 1] + [" | ".join(r[len(header) - 1 :])]
            data = {header[k].strip(): r[k].strip() for k in range(len(header))}
            entries.append({"h2": h2, "h3": h3, "h4": h4, "data": data})

    return entries


def classify(entry: dict[str, Any]) -> dict[str, str]:
    h3 = entry["h3"]
    h4 = entry["h4"]

    if h3.startswith("### 1.1"):
        return {"group": "survey", "paradigm": "Survey", "task": "Survey"}
    if h3.startswith("### 1.2"):
        return {"group": "benchmark", "paradigm": "Benchmark", "task": "Benchmark"}

    if h3.startswith("### 2.1"):
        return {"group": "metabbo", "paradigm": "RL", "task": normalize_task_from_h4(h4)}
    if h3.startswith("### 2.2"):
        return {"group": "metabbo", "paradigm": "SL", "task": normalize_task_from_h4(h4)}
    if h3.startswith("### 2.3"):
        return {"group": "metabbo", "paradigm": "NE", "task": normalize_task_from_h4(h4)}
    if h3.startswith("### 2.4"):
        return {"group": "metabbo", "paradigm": "ICL", "task": normalize_task_from_h4(h4)}

    if h3.startswith("### 3.1"):
        return {"group": "others", "paradigm": "Other", "task": "Evaluation Indicator"}
    if h3.startswith("### 3.2"):
        return {"group": "others", "paradigm": "Other", "task": "Landscape Feature"}
    if h3.startswith("### 3.3"):
        return {"group": "others", "paradigm": "Other", "task": "Application"}

    return {"group": "other", "paradigm": "Other", "task": "Other"}


def get_field(data: dict[str, str], names: list[str]) -> str:
    for n in names:
        if n in data and data[n].strip():
            return data[n].strip()
    return "-"


def render_survey_bench(entries: list[dict[str, Any]], out_file: Path) -> None:
    survey = [e for e in entries if e["cls"]["group"] == "survey"]
    bench = [e for e in entries if e["cls"]["group"] == "benchmark"]

    survey_rows = [[get_field(e["data"], ["Paper"])] for e in survey]
    bench_rows = [
        [
            get_field(e["data"], ["Benchmark"]),
            get_field(e["data"], ["Paper"]),
            get_field(e["data"], ["Code Resource", "Code"]),
            get_field(e["data"], ["Optimization Type"]),
        ]
        for e in bench
    ]

    text = "\n".join(
        [
            "# Survey Papers & Benchmarks",
            "",
            "## Survey Papers",
            "",
            md_table(["Paper"], survey_rows),
            "",
            "## Benchmarks",
            "",
            md_table(["Benchmark", "Paper", "Code Resource", "Optimization Type"], bench_rows),
            "",
        ]
    )
    out_file.write_text(text, encoding="utf-8")


def render_metabbo(entries: list[dict[str, Any]], out_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for paradigm, fname in [("RL", "rl.md"), ("SL", "sl.md"), ("NE", "ne.md"), ("ICL", "icl.md")]:
        subset = [e for e in entries if e["cls"]["group"] == "metabbo" and e["cls"]["paradigm"] == paradigm]
        counts[paradigm] = len(subset)
        by_task: dict[str, list[dict[str, Any]]] = {"AS": [], "AC": [], "AG": [], "SM": [], "Other": []}
        for e in subset:
            by_task.setdefault(e["cls"]["task"], []).append(e)

        lines = [f"# MetaBBO via {paradigm}", ""]
        for task in ["AS", "AC", "AG", "SM", "Other"]:
            rows = by_task.get(task, [])
            if not rows:
                continue
            lines.extend([f"## {task}", ""])
            header = ["Algorithm", "Paper", "Optimization Type", "Low-Level Optimizer", "Learning Method", "Code Resource"]
            table_rows = []
            for e in rows:
                d = e["data"]
                table_rows.append(
                    [
                        get_field(d, ["Algorithm", "Method", "Feature", "Indicator", "Benchmark", "Paper"]),
                        get_field(d, ["Paper"]),
                        get_field(d, ["Optimization Type", "Application"]),
                        get_field(d, ["Low-Level Optimizer"]),
                        get_field(d, ["RL", "Learning paradigm", "Automated algorithm design task"]),
                        get_field(d, ["Code Resource", "Code"]),
                    ]
                )
            lines.extend([md_table(header, table_rows), ""])

        (out_dir / fname).write_text("\n".join(lines), encoding="utf-8")

    # metabbo index
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# MetaBBO Papers",
                "",
                "- [MetaBBO-RL](./rl.md)",
                "- [MetaBBO-SL](./sl.md)",
                "- [MetaBBO-NE](./ne.md)",
                "- [MetaBBO-ICL](./icl.md)",
                "",
                "## Notes",
                "",
                "- Content is synchronized from `MetaEvo/Awesome-MetaBBO`.",
                "- Sections are grouped by paradigm and task (`AS/AC/AG/SM`).",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return counts


def render_others(entries: list[dict[str, Any]], out_file: Path) -> int:
    subset = [e for e in entries if e["cls"]["group"] == "others"]
    by_task: dict[str, list[dict[str, Any]]] = {
        "Evaluation Indicator": [],
        "Landscape Feature": [],
        "Application": [],
    }
    for e in subset:
        by_task.setdefault(e["cls"]["task"], []).append(e)

    lines = ["# Others", ""]

    # 3.1
    rows = by_task.get("Evaluation Indicator", [])
    lines.extend(["## Evaluation Indicator", ""])
    lines.append(md_table(["Indicator", "Paper"], [[get_field(e["data"], ["Indicator", "Feature", "Algorithm"]), get_field(e["data"], ["Paper"])] for e in rows]))
    lines.append("")

    # 3.2
    rows = by_task.get("Landscape Feature", [])
    lines.extend(["## Landscape Feature", ""])
    lines.append(md_table(["Feature", "Paper"], [[get_field(e["data"], ["Feature", "Indicator", "Algorithm"]), get_field(e["data"], ["Paper"])] for e in rows]))
    lines.append("")

    # 3.3
    rows = by_task.get("Application", [])
    lines.extend(["## Application", ""])
    lines.append(
        md_table(
            ["Algorithm", "Paper", "Learning Paradigm", "Automated Algorithm Design Task", "Code", "Application"],
            [
                [
                    get_field(e["data"], ["Algorithm"]),
                    get_field(e["data"], ["Paper"]),
                    get_field(e["data"], ["Learning paradigm"]),
                    get_field(e["data"], ["Automated algorithm design task"]),
                    get_field(e["data"], ["Code"]),
                    get_field(e["data"], ["Application"]),
                ]
                for e in rows
            ],
        )
    )
    lines.append("")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    return len(subset)


def render_csv(entries: list[dict[str, Any]], out_file: Path) -> int:
    fieldnames = [
        "id",
        "group",
        "paradigm",
        "task",
        "item",
        "paper",
        "optimization_type",
        "low_level_optimizer",
        "learning_method",
        "code_resource",
        "source_h3",
        "source_h4",
    ]
    rows = []
    for idx, e in enumerate(entries, start=1):
        d = e["data"]
        item = get_field(d, ["Algorithm", "Method", "Benchmark", "Indicator", "Feature", "Paper"])
        paper = get_field(d, ["Paper"])
        row = {
            "id": f"ambbo-{idx:04d}-{slug(item)[:24]}",
            "group": e["cls"]["group"],
            "paradigm": e["cls"]["paradigm"],
            "task": e["cls"]["task"],
            "item": item,
            "paper": paper,
            "optimization_type": get_field(d, ["Optimization Type", "Application"]),
            "low_level_optimizer": get_field(d, ["Low-Level Optimizer"]),
            "learning_method": get_field(d, ["RL", "Learning paradigm", "Automated algorithm design task"]),
            "code_resource": get_field(d, ["Code Resource", "Code"]),
            "source_h3": e["h3"],
            "source_h4": e["h4"],
        }
        rows.append(row)

    with out_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def render_papers_readme(repo_root: Path, counts: dict[str, int], total_rows: int, source: str) -> None:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p = repo_root / "papers" / "README.md"
    p.write_text(
        "\n".join(
            [
                "# MetaBBO Paper Library",
                "",
                "Structured paper list synchronized from Awesome-MetaBBO and rendered for GitHub browsing.",
                "",
                f"- Sync source: `{source}`",
                f"- Last sync: `{now}`",
                f"- Total entries: `{total_rows}`",
                "",
                "## Content",
                "",
                "- [1. Survey Papers & Benchmarks](./survey-and-benchmarks.md)",
                "- [2. MetaBBO](./metabbo/README.md)",
                f"  - [2.1 MetaBBO via Reinforcement Learning ({counts.get('RL', 0)})](./metabbo/rl.md)",
                f"  - [2.2 MetaBBO via Supervised Learning ({counts.get('SL', 0)})](./metabbo/sl.md)",
                f"  - [2.3 MetaBBO via Neuroevolution ({counts.get('NE', 0)})](./metabbo/ne.md)",
                f"  - [2.4 MetaBBO via In-Context Learning ({counts.get('ICL', 0)})](./metabbo/icl.md)",
                "- [3. Others](./others.md)",
                "- [4. Structured Metadata (CSV)](./library.csv)",
                "- [5. Paper Entry Template](./templates/paper-template.md)",
                "",
                "## Update Rules",
                "",
                "1. Prefer running `papers/scripts/sync_from_awesome_metabbo.py` for bulk updates.",
                "2. Keep markdown files and `library.csv` in sync.",
                "3. Preserve source wording from Awesome-MetaBBO when auto-syncing.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def render_root_readme(repo_root: Path) -> None:
    p = repo_root / "README.md"
    p.write_text(
        "\n".join(
            [
                "# MetaBBO-Frontier",
                "",
                "A repository for tracking and organizing Meta-Black-Box-Optimization (MetaBBO) research.",
                "",
                "## Paper Library",
                "",
                "The paper library is synchronized from Awesome-MetaBBO and rendered in this repository for GitHub visualization:",
                "",
                "- [papers/README.md](./papers/README.md)",
                "",
                "## Auto Sync",
                "",
                "- Local sync script: `papers/scripts/sync_from_awesome_metabbo.py`",
                "- GitHub Action workflow: `.github/workflows/sync-awesome-metabbo.yml`",
                "",
                "## Research Background",
                "",
                "- `Toward_Automated_Algorithm_Design_A_Survey_and_Practical_Guide_to_Meta-Black-Box-Optimization.pdf`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync paper library from Awesome-MetaBBO markdown tables.")
    parser.add_argument("--source", default=SOURCE_URL, help="Source README path or URL.")
    parser.add_argument("--repo-root", default=".", help="Target repository root.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    papers_dir = repo_root / "papers"
    metabbo_dir = papers_dir / "metabbo"
    metabbo_dir.mkdir(parents=True, exist_ok=True)

    text = fetch_text(args.source)
    raw_entries = parse_tables(text)
    for e in raw_entries:
        e["cls"] = classify(e)

    # Keep only 1/2/3 content groups
    entries = [e for e in raw_entries if e["cls"]["group"] in {"survey", "benchmark", "metabbo", "others"}]

    render_survey_bench(entries, papers_dir / "survey-and-benchmarks.md")
    paradigm_counts = render_metabbo(entries, metabbo_dir)
    others_count = render_others(entries, papers_dir / "others.md")
    total_rows = render_csv(entries, papers_dir / "library.csv")
    render_papers_readme(repo_root, paradigm_counts, total_rows, args.source)
    render_root_readme(repo_root)

    # keep template if missing
    t = papers_dir / "templates" / "paper-template.md"
    t.parent.mkdir(parents=True, exist_ok=True)
    if not t.exists():
        t.write_text("# Paper Entry Template\n", encoding="utf-8")

    print(
        f"synced entries={total_rows} survey+bench={sum(1 for e in entries if e['cls']['group'] in {'survey','benchmark'})} "
        f"rl={paradigm_counts.get('RL',0)} sl={paradigm_counts.get('SL',0)} ne={paradigm_counts.get('NE',0)} icl={paradigm_counts.get('ICL',0)} others={others_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
