#!/usr/bin/env python3
"""Generate daily newsletter JSON and Markdown from cluster summaries."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.paths import cluster_summaries_dir
from enrichment.schemas import ClusterSummary, Newsletter, NewsletterItem, NewsletterSection

# Map topic keywords to section names
_TOPIC_SECTION_MAP = [
    (["política", "governo", "congresso", "senado", "câmara", "eleição", "presidente", "lula", "bolsonaro"], "Política"),
    (["economia", "mercado", "bolsa", "dólar", "inflação", "banco", "pib", "fiscal", "tributário"], "Economia"),
    (["esporte", "futebol", "copa", "campeonato", "nba", "olimpíadas", "corrida"], "Esportes"),
    (["tecnologia", "ia", "inteligência artificial", "startup", "apple", "google", "meta", "openai"], "Tecnologia"),
    (["saúde", "vacina", "pandemia", "sus", "hospital", "medicina", "doença"], "Saúde"),
    (["internacional", "eua", "china", "rússia", "ucrânia", "trump", "guerra", "otan"], "Internacional"),
    (["segurança", "crime", "violência", "polícia", "tráfico", "assassinato", "operação"], "Segurança"),
]


def _infer_section(cluster_summary: ClusterSummary, cluster_title: str = "") -> str:
    text = (cluster_summary.neutralHeadline + " " + cluster_summary.whatHappened + " " + cluster_title).lower()
    for keywords, section in _TOPIC_SECTION_MAP:
        if any(kw in text for kw in keywords):
            return section
    return "Geral"


def _to_newsletter_item(cs: ClusterSummary) -> NewsletterItem:
    coverage_note = ""
    if cs.coverageDifferences:
        parts = [f"{cd.bucket}: {cd.summary}" for cd in cs.coverageDifferences[:2]]
        coverage_note = "; ".join(parts)
    elif cs.headlineDivergence.level != "low":
        coverage_note = cs.headlineDivergence.explanation

    return NewsletterItem(
        clusterId=cs.clusterId,
        title=cs.neutralHeadline,
        summary=cs.newsletterBlurb or cs.neutralSummary,
        whyItMatters=cs.whyItMatters,
        coverageNote=coverage_note,
        confidence=cs.confidence,
    )


def generate_newsletter(
    date: str,
    summaries_dir: Path,
    output_json: Path,
    output_md: Path,
    max_items: int = 20,
    cluster_meta: dict[str, dict] | None = None,
) -> Newsletter:
    cluster_meta = cluster_meta or {}
    summaries: list[ClusterSummary] = []
    for path in summaries_dir.glob("*.json"):
        try:
            summaries.append(ClusterSummary.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"  SKIP {path.name}: {e}", file=sys.stderr)

    summaries = summaries[:max_items]

    # Group into sections
    sections_map: dict[str, list[NewsletterItem]] = {}
    for cs in summaries:
        meta = cluster_meta.get(cs.clusterId, {})
        section = _infer_section(cs, meta.get("title", ""))
        item = _to_newsletter_item(cs)
        sections_map.setdefault(section, []).append(item)

    # Order sections predictably
    ordered_sections = ["Política", "Economia", "Internacional", "Segurança", "Saúde", "Esportes", "Tecnologia", "Geral"]
    sections = [
        NewsletterSection(name=name, items=sections_map[name])
        for name in ordered_sections
        if name in sections_map
    ]
    # Any sections not in the ordered list
    for name, items in sections_map.items():
        if name not in ordered_sections:
            sections.append(NewsletterSection(name=name, items=items))

    newsletter = Newsletter(
        date=date,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        title="GNewsBR — Resumo do dia",
        intro=f"As principais histórias do dia {date}, coletadas e analisadas automaticamente.",
        sections=sections,
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(newsletter.model_dump_json(indent=2), encoding="utf-8")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_to_markdown(newsletter), encoding="utf-8")

    print(f"Newsletter: {sum(len(s.items) for s in sections)} items across {len(sections)} sections")
    return newsletter


def _to_markdown(nl: Newsletter) -> str:
    lines = [
        f"# {nl.title}",
        f"\nData: {nl.date}",
        "",
    ]
    for section in nl.sections:
        lines.append(f"## {section.name}")
        lines.append("")
        for item in section.items:
            lines.append(f"### {item.title}")
            lines.append("")
            lines.append(item.summary)
            lines.append("")
            if item.whyItMatters:
                lines.append(f"**Por que importa:** {item.whyItMatters}")
                lines.append("")
            if item.coverageNote:
                lines.append(f"**Como a cobertura variou:** {item.coverageNote}")
                lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--cluster-summaries-dir", default=None)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-md", default=None)
    parser.add_argument("--max-items", type=int, default=20)
    args = parser.parse_args()

    from datetime import datetime, timezone
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from enrichment.paths import ENRICHMENT_PUBLIC, cluster_summaries_dir as csd
    summaries = Path(args.cluster_summaries_dir) if args.cluster_summaries_dir else csd(date)
    output_json = Path(args.output_json) if args.output_json else ENRICHMENT_PUBLIC / "newsletters" / f"{date}.json"
    output_md = Path(args.output_md) if args.output_md else ENRICHMENT_PUBLIC / "newsletters" / f"{date}.md"

    generate_newsletter(date, summaries, output_json, output_md, args.max_items)


if __name__ == "__main__":
    main()
