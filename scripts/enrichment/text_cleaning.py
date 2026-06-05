from __future__ import annotations

import re

_BOILERPLATE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"gostaria de receber as principais not[ií]cias",
        r"n[aã]o,?\s*obrigad[oa]",
        r"sim,?\s*(aceito|quero)",
        r"assine\s*(a\s*folha|o\s*globo|o\s*estadão|agora)?$",
        r"^ASSINE\b",
        r"minha\s*(folha|assinatura|conta)",
        r"newsletters?$",
        r"forma de pagamento",
        r"editar senha",
        r"^atendimento$",
        r"^sair$",
        r"copiar link",
        r"salvar para ler depois",
        r"recurso exclusivo para assinantes",
        r"^compartilhe[:\s]*$",
        r"^facebook$",
        r"^whatsapp$",
        r"^linkedin$",
        r"^e-?mail$",
        r"^carregando\.{0,3}$",
        r"^leia mais[:\s]*$",
        r"^mais lidas?\b",
        r"^ver todas?$",
        r"^veja v[ií]deos?$",
        r"t[oó]picos? relacionados?",
        r"envie sua not[ií]cia",
        r"erramos\??$",
        r"^ombudsman$",
        r"copyright\b",
        r"^modal\s*\d+$",
        r"ok newsletter",
        r"cadastro realizado com sucesso",
        r"por favor,?\s*tente mais tarde",
        r"continua ap[oó]s a publicidade",
        r"^publicidade$",
        r"^anúncio$",
        r"ver todos? os artigos",
        r"^tags?:\s",
        r"gostou\?\s*compartilhe",
        r"ajude mais pessoas",
        r"not[ií]cias relacionadas$",
        r"^leia mais sobre\b",
        r"^voltar ao topo$",
        r"enviar por e-?mail",
        r"imprimir esta p[aá]gina",
    ]
]

_BLANK_LINE = re.compile(r"^\s*$")
_SHORT_LINE = re.compile(r"^.{1,15}$")


def _is_boilerplate(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def clean_boilerplate(text: str) -> tuple[str, float]:
    """Remove boilerplate lines. Returns (clean_text, removed_ratio)."""
    lines = text.splitlines()
    original_count = len(lines)

    kept: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if _is_boilerplate(stripped):
            continue
        if stripped in seen and len(stripped) < 60:
            continue
        seen.add(stripped)
        kept.append(line)

    clean = "\n".join(kept).strip()
    removed = original_count - len(kept)
    ratio = removed / original_count if original_count else 0.0
    return clean, ratio
