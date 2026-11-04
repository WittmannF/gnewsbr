"""The 15 homepage summaries must belong to the exact index being published."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from requests.exceptions import Timeout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from summarize_home import read_json, run, sources_for


class Top15BriefTests(unittest.TestCase):
    def make_home(self, root: Path, count: int = 15) -> list[str]:
        clusters = []
        for i in range(count):
            cid = f"story_{i:012x}"
            relative = f"data/clusters/latest/{cid}.json"
            clusters.append({"id": cid, "title": f"Evento {i}",
                             "summary": f"Resumo original {i}", "detailPath": relative})
            path = root / "public" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "id": cid, "title": f"Evento {i}", "summary": f"Resumo original {i}",
                "articles": [
                    {"url": f"https://news{n}.example/noticia{i}", "title": f"Fonte {n}: Evento {i}",
                     "description": f"O veículo {n} descreve o acontecimento de forma própria.",
                     "source": f"Jornal {n}"} for n in range(3)
                ],
            }), encoding="utf-8")
        index = root / "public/data/latest.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(json.dumps({"generatedAt": "2026-11-01T12:00:00Z",
                                     "clusters": clusters}), encoding="utf-8")
        return [c["id"] for c in clusters]

    def test_generate_all_15_once_and_reuse_with_no_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.make_home(root)
            with patch("summarize_home.call_model", return_value="Resumo fundamentado nas manchetes e nas descrições das três fontes originais disponíveis.") as model:
                first = run(root, api_key="test-key")
            self.assertEqual(first["top15Covered"], 15)
            self.assertEqual(first["generated"], 15)
            self.assertEqual(model.call_count, 15)
            with patch("summarize_home.call_model") as model:
                second = run(root, api_key="")
            self.assertEqual(second["top15Covered"], 15)
            self.assertEqual(second["generated"], 0)
            model.assert_not_called()
            index = read_json(root / "public/data/latest.json")
            for c in index["clusters"]:
                self.assertEqual(c["title"], f"Evento {ids.index(c['id'])}")
                self.assertTrue(c["aiSummary"])
                self.assertEqual(len(c["aiSources"]), 3)
                detail = read_json(root / "public" / c["detailPath"])
                self.assertEqual(detail["aiSummary"], c["aiSummary"])
            self.assertEqual(len(list((root / "public/data/enrichment/briefs").glob("*.json"))), 15)

    def test_missing_key_does_not_publish_fake_ai_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_home(root, count=2)
            report = run(root, api_key="")
            self.assertEqual(report["top15Covered"], 0)
            self.assertEqual(set(report["reasons"].values()), {"missing_api_key"})
            self.assertNotIn("aiSummary", read_json(root / "public/data/latest.json")["clusters"][0])

    def test_failed_story_is_not_charged_and_retried_again_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.make_home(root, count=1)
            with patch("summarize_home.call_model", side_effect=Timeout("temporary")) as model:
                first = run(root, api_key="test-key")
                second = run(root, api_key="test-key")
            self.assertEqual(model.call_count, 1)
            self.assertEqual(first["reasons"][ids[0]], "llm_error")
            self.assertEqual(second["reasons"][ids[0]], "already_attempted_today")
            ledger_dir = root / "data/enrichment/cost-ledger"
            ledgers = list(ledger_dir.glob("*.json"))
            self.assertEqual(len(ledgers), 1)
            ledger = read_json(ledgers[0])
            self.assertEqual(ledger["estimatedCostUsd"], 0.01)
            self.assertEqual([e["kind"] for e in ledger["events"]],
                             ["brief_reserved", "brief_failed"])

    def test_existing_snapshot_summary_is_reused_without_cache_or_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.make_home(root, count=1)
            home_path = root / "public/data/latest.json"
            home = read_json(home_path)
            home["clusters"][0]["aiSummary"] = "Resumo de IA já publicado"
            home["clusters"][0]["aiSources"] = [{"source": "Jornal 0", "url": "https://news0.example/noticia0"}]
            home_path.write_text(json.dumps(home), encoding="utf-8")
            with patch("summarize_home.call_model") as model:
                result = run(root, api_key="test-key")
            self.assertEqual(result["generated"], 0)
            self.assertEqual(result["top15Covered"], 1)
            detail = read_json(root / "public/data/clusters/latest" / f"{ids[0]}.json")
            self.assertEqual(detail["aiSummary"], "Resumo de IA já publicado")
            cached = read_json(root / "public/data/enrichment/briefs" / f"{ids[0]}.json")
            self.assertEqual(cached["summary"], "Resumo de IA já publicado")
            model.assert_not_called()

    def test_reserved_batch_persists_ledger_before_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.make_home(root, count=2)
            batch_id, day = "test-run-1", "2026-11-03"
            with patch("summarize_home.call_model") as model:
                prepared = run(root, api_key="key", reserve_only=True,
                               batch_id=batch_id, ledger_date=day)
            self.assertEqual(prepared["reserved"], 2)
            self.assertEqual(prepared["generated"], 0)
            model.assert_not_called()
            ledger_path = root / "data/enrichment/cost-ledger" / f"{day}.json"
            before = read_json(ledger_path)
            self.assertEqual(before["estimatedCostUsd"], 0.02)
            self.assertEqual([e["clusterId"] for e in before["events"]], ids)
            self.assertTrue(all(e["batchId"] == batch_id for e in before["events"]))

            # A different Actions run on the same UTC day must not reserve
            # the same cluster again, even if the original job was cancelled.
            with patch("summarize_home.call_model") as model:
                duplicate = run(root, api_key="key", reserve_only=True,
                                batch_id="different-run", ledger_date=day)
            self.assertEqual(duplicate["reserved"], 0)
            self.assertEqual(read_json(ledger_path)["estimatedCostUsd"], 0.02)
            model.assert_not_called()

            with patch("summarize_home.call_model",
                       return_value="Resumo de IA gerado após a reserva no ledger.") as model:
                published = run(root, api_key="key", reserved_batch=batch_id,
                                ledger_date=day)
            self.assertEqual(model.call_count, 2)
            self.assertEqual(published["generated"], 2)
            self.assertEqual(read_json(ledger_path)["estimatedCostUsd"], 0.02)

            # Even if GitHub Actions retries the same execution, this batch is
            # already finalized and should make zero additional paid calls.
            with patch("summarize_home.call_model") as model:
                rerun = run(root, api_key="key", reserved_batch=batch_id,
                            ledger_date=day)
            self.assertEqual(rerun["generated"], 0)
            model.assert_not_called()

    def test_uncommitted_batch_is_not_authorized_to_call_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_home(root, count=1)
            with patch("summarize_home.call_model") as model:
                result = run(root, api_key="key", reserved_batch="not-pushed",
                             ledger_date="2026-11-03")
            self.assertEqual(result["generated"], 0)
            model.assert_not_called()

    def test_hourly_rehydration_keeps_cached_summaries_without_payment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.make_home(root, count=1)
            with patch("summarize_home.call_model", return_value=(
                "Resumo de IA preservado mesmo depois da nova coleta horária.")):
                run(root, api_key="key")
            index = root / "public/data/latest.json"
            detail = root / "public/data/clusters/latest" / f"{ids[0]}.json"
            # Simulates the hourly collector resetting both files.
            self.make_home(root, count=1)
            self.assertNotIn("aiSummary", read_json(index)["clusters"][0])
            with patch("summarize_home.call_model") as model:
                restored = run(root, api_key="", max_new=0)
            self.assertEqual(restored["generated"], 0)
            self.assertEqual(restored["top15Covered"], 1)
            self.assertIn("aiSummary", read_json(index)["clusters"][0])
            self.assertIn("aiSummary", read_json(detail))
            model.assert_not_called()

    def test_source_selection_limits_five_and_deduplicates_publishers(self):
        arts = [
            {"title": f"Artigo {i}", "description": "Descrição disponível",
             "source": f"Veículo {i}", "url": f"https://site{i % 6}.example/news/{i}"}
            for i in range(10)
        ]
        selected = sources_for({"articles": arts})
        self.assertEqual(len(selected), 5)
        self.assertEqual(len({s["url"].split("/")[2] for s in selected}), 5)

    def test_insufficient_sources_preserves_original_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.make_home(root, count=1)
            path = root / "public/data/clusters/latest" / f"{ids[0]}.json"
            data = read_json(path)
            data["articles"] = data["articles"][:1]
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch("summarize_home.call_model") as model:
                report = run(root, api_key="test-key")
            self.assertEqual(report["reasons"][ids[0]], "insufficient_sources")
            self.assertNotIn("aiSummary", read_json(root / "public/data/latest.json")["clusters"][0])
            model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
