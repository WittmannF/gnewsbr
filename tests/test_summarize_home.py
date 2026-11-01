"""The 15 homepage summaries must belong to the exact index being published."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
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
