#!/usr/bin/env python3
"""Generate structured LLM summaries for clusters based on article summaries."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from enrichment.llm_client import LLMClient, make_client
from enrichment.paths import article_summaries_dir, cluster_summaries_dir
from enrichment.prompts import CLUSTER_SUMMARY_SYSTEM, build_cluster_user_prompt
from enrichment.schemas import ArticleSummary, ClusterSummary, HeadlineDivergence


def summarize_clusters(
    date: str,
    selected_path: Path,
    summaries_dir: Path,
    output_dir: Path,
    client: LLMClient,
    model: str,
    prompt_version: str,
) -> tuple[list[ClusterSummary], list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selection = json.loads(selected_path.read_text(encoding="utf-8"))

    # Load article summaries
    summary_map: dict[str, ArticleSummary] = {}
    for path in summaries_dir.glob("*.json"):
        try:
            s = ArticleSummary.model_validate_json(path.read_text(encoding="utf-8"))
            summary_map[s.archiveId] = s
        except Exception:
            pass

    results: list[ClusterSummary] = []
    errors: list[dict] = []

    for cluster in selection.get("clusters", []):
        cluster_id = cluster["clusterId"]
        archive_ids = cluster.get("selectedArticles", [])

        article_summaries = [summary_map[aid] for aid in archive_ids if aid in summary_map]
        if not article_summaries:
            errors.append({"clusterId": cluster_id, "stage": "summarize_cluster", "error": "no_article_summaries"})
            continue

        # Check cache
        out_path = output_dir / f"{cluster_id}.json"
        if out_path.exists():
            try:
                existing = ClusterSummary.model_validate_json(out_path.read_text(encoding="utf-8"))
                if existing.model == model and existing.promptVersion == prompt_version:
                    results.append(existing)
                    continue
            except Exception:
                pass

        try:
            raw = client.generate_json(
                CLUSTER_SUMMARY_SYSTEM,
                build_cluster_user_prompt([s.model_dump() for s in article_summaries]),
                schema_name="cluster_summary",
            )
        except Exception as e:
            errors.append({"clusterId": cluster_id, "stage": "summarize_cluster", "error": str(e)})
            continue

        try:
            divergence_raw = raw.get("headlineDivergence", {})
            cluster_summary = ClusterSummary(
                clusterId=cluster_id,
                model=model,
                promptVersion=prompt_version,
                generatedAt=datetime.now(timezone.utc).isoformat(),
                neutralHeadline=raw.get("neutralHeadline", cluster.get("clusterTitle", "")),
                neutralSummary=raw.get("neutralSummary", ""),
                whatHappened=raw.get("whatHappened", ""),
                whyItMatters=raw.get("whyItMatters", ""),
                knownFacts=raw.get("knownFacts", []),
                reportedClaims=raw.get("reportedClaims", []),
                coverageDifferences=raw.get("coverageDifferences", []),
                headlineDivergence=HeadlineDivergence(
                    level=divergence_raw.get("level", "low"),
                    explanation=divergence_raw.get("explanation", ""),
                ),
                openQuestions=raw.get("openQuestions", []),
                newsletterBlurb=raw.get("newsletterBlurb", ""),
                confidence=raw.get("confidence", "medium"),
            )
        except Exception as e:
            errors.append({"clusterId": cluster_id, "stage": "summarize_cluster", "error": f"schema_validation: {e}"})
            continue

        out_path.write_text(cluster_summary.model_dump_json(indent=2), encoding="utf-8")
        results.append(cluster_summary)

    print(f"Cluster summaries: {len(results)} generated, {len(errors)} errors")
    return results, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--selected-articles", default=None)
    parser.add_argument("--article-summaries-dir", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--prompt-version", default="cluster-summary-v1")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    from datetime import datetime, timezone
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from enrichment.paths import ENRICHMENT_DATA
    selected = Path(args.selected_articles) if args.selected_articles else ENRICHMENT_DATA / "selected-articles" / f"{date}.json"
    summaries = Path(args.article_summaries_dir) if args.article_summaries_dir else article_summaries_dir(date)
    out_dir = Path(args.output_dir) if args.output_dir else cluster_summaries_dir(date)
    model = args.model or "llama3.2:3b"

    client = make_client(model=model, mock=args.mock)
    summarize_clusters(date, selected, summaries, out_dir, client, model, args.prompt_version)


if __name__ == "__main__":
    main()
