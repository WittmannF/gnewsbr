# Metodologia de classificação editorial

Esta base classifica a **linha editorial percebida** das fontes usadas pelo GNewsBR. Ela não é uma nota de qualidade, credibilidade, factualidade ou confiabilidade.

## Escala política/editorial

- `1`: progressista forte / esquerda explícita
- `2`: progressista
- `3`: centro-progressista
- `4`: centro a centro-progressista
- `5`: centro, institucional, local, agregador ou sem viés nacional claro
- `6`: centro a centro-conservador / liberal econômico moderado
- `7`: centro-conservador
- `8`: conservador
- `9`: conservador forte
- `10`: conservador forte / linha militante

## Campos principais

- `name`: nome canônico da fonte.
- `spectrum_score`: posição na escala 1-10.
- `spectrum_bucket`: bucket usado pela UI (`left`, `centerLeft`, `center`, `centerRight`, `right`).
- `spectrum_label`: rótulo legível para humanos.
- `type`: tipo da fonte: `editorial`, `official`, `business`, `local`, `aggregator`, `entertainment` ou `sector`.
- `scope`: abrangência principal: `national`, `regional`, `local` ou `international`.
- `political_weight`: peso sugerido em cálculos políticos. Fontes oficiais, locais, agregadores e entretenimento devem pesar menos que veículos editoriais nacionais.
- `confidence`: confiança da classificação: `low`, `medium` ou `high`.
- `review_status`: `draft`, `reviewed` ou `disputed`.
- `rationale`: justificativa curta para a classificação.

## Regras de revisão

1. Classifique a fonte pela linha editorial pública e recorrente, não por uma matéria isolada.
2. Separe **posição política** de **credibilidade**. Uma fonte pode estar em qualquer ponto do espectro e ainda assim ser confiável ou problemática.
3. Fontes oficiais (`GOV.BR`, Senado, governos estaduais) devem ser `type: official`, normalmente `spectrum_score: 5`, com `political_weight` baixo.
4. Agregadores (`MSN`, alguns portais republicadores) devem apontar para a fonte original quando possível.
5. Fontes locais sem linha nacional clara devem ficar próximas de `5`, com `confidence: low` ou `medium`.
6. Fontes econômicas podem ter `spectrum_score: 6` por viés liberal/mercado sem necessariamente serem conservadoras em costumes.
7. Classificações controversas devem usar `review_status: disputed` e explicar a divergência no `rationale` ou em `notes`.

## Como contribuir

Abra um PR alterando `source-spectrum.yml` e/ou `source-aliases.yml`. Use `review-template.md` como guia e rode:

```bash
python3 scripts/validate_sources.py
python3 scripts/build_source_map.py
```
