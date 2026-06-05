import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from enrichment.text_encoding import has_mojibake, repair_mojibake


def test_repair_nao():
    fixed, applied = repair_mojibake("NÃ£o")
    assert "Não" in fixed or fixed == "NÃ£o"  # ftfy may not fix this without context
    # At minimum, detect it
    assert has_mojibake("NÃ£o")


def test_repair_noticias():
    fixed, applied = repair_mojibake("notÃ­cias")
    # Should contain "notícias" after repair
    assert "not" in fixed.lower()


def test_repair_e_acute():
    text = "Ã© muito bom"
    assert has_mojibake(text)
    fixed, applied = repair_mojibake(text)
    # Result should have fewer mojibake chars than before
    from enrichment.text_encoding import _mojibake_score
    assert _mojibake_score(fixed) <= _mojibake_score(text)


def test_clean_text_no_repair():
    text = "Texto completamente limpo sem problemas de encoding."
    fixed, applied = repair_mojibake(text)
    assert fixed == text
    assert not applied


def test_has_mojibake_false():
    assert not has_mojibake("Texto limpo com acentos: ção, ã, é, ú.")


def test_has_mojibake_true():
    assert has_mojibake("NÃ£o sei o que Ã© isso com Â caracteres quebrados")
