import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from enrichment.text_cleaning import clean_boilerplate

_FOLHA_SAMPLE = """
Pai de Henry criticou o perdão judicial concedido à professora Monique Medeiros.

Gostaria de receber as principais notícias?
Não, obrigado

ASSINE A FOLHA

Salvar para ler depois

O perdão judicial concedido à professora Monique Medeiros, mãe de Henry Borel, gerou revolta no pai da criança.

"Mataram o meu filho pela terceira vez", disse Leniel Borel em entrevista.

O advogado de Leniel vai apresentar recurso contra a decisão.

Mais lidas em Cotidiano

Copyright Folha de S.Paulo

OK NEWSLETTER
"""


def test_removes_assine():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "ASSINE A FOLHA" not in clean


def test_removes_salvar():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "Salvar para ler depois" not in clean


def test_removes_mais_lidas():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "Mais lidas" not in clean


def test_removes_copyright():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "Copyright" not in clean


def test_removes_ok_newsletter():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "OK NEWSLETTER" not in clean


def test_preserves_quote():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "Mataram o meu filho pela terceira vez" in clean


def test_preserves_monique():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "Monique Medeiros" in clean


def test_preserves_recurso():
    clean, _ = clean_boilerplate(_FOLHA_SAMPLE)
    assert "recurso" in clean.lower()


def test_removed_ratio_positive():
    _, ratio = clean_boilerplate(_FOLHA_SAMPLE)
    assert ratio > 0
