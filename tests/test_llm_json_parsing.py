import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from enrichment.llm_client import MockLLMClient, _extract_json


def test_extract_plain_json():
    text = '{"key": "value", "num": 42}'
    result = _extract_json(text)
    assert result == {"key": "value", "num": 42}


def test_extract_json_with_markdown_fence():
    text = "```json\n{\"key\": \"value\"}\n```"
    result = _extract_json(text)
    assert result["key"] == "value"


def test_extract_json_embedded_in_text():
    text = 'Here is the result: {"summary": "ok", "confidence": "high"} done.'
    result = _extract_json(text)
    assert result["summary"] == "ok"


def test_mock_client_article_summary():
    client = MockLLMClient()
    result = client.generate_json("system", "user", schema_name="article_summary")
    assert "summary" in result
    assert "whatHappened" in result
    assert result["confidence"] == "low"


def test_mock_client_cluster_summary():
    client = MockLLMClient()
    result = client.generate_json("system", "user", schema_name="cluster_summary")
    assert "neutralHeadline" in result
    assert "newsletterBlurb" in result
    assert "headlineDivergence" in result
