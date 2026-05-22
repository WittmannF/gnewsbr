# GNewsBR

Web app brasileiro inspirado no Ground News. O MVP usa clusters/stories do Google News Brasil como agrupamento inicial, aplica metadados editoriais manuais por fonte e exibe comparação de cobertura em uma UI React responsiva.

## Status

Protótipo visual local com dados reais coletados do Google News Brasil. A coleta atual descobre stories a partir de **Manchetes/Home + tópicos encontrados no menu do Google News**, abre cada `/stories/<id>` e gera `public/data/latest.json` com título, resumo, fonte, link, horário e distribuição editorial estimada.

Na última coleta local: **347 stories encontrados/coletados** e **5.937 artigos relacionados**.

## Comandos

```bash
npm install
pip install -r requirements.txt
npm run sources:validate  # valida data/sources/source-spectrum.yml e aliases
npm run sources:build     # gera public/data/source-spectrum.json
npm run collect           # gera public/data/latest.json
npm run dev -- --host 0.0.0.0 --port 4177
npm run build
npm run preview -- --host 0.0.0.0 --port 4177
```

## Revisão colaborativa das fontes

A classificação editorial das fontes fica fora do código, em arquivos revisáveis por PR:

- `data/sources/source-spectrum.yml`: fonte canônica, score 1-10, tipo, peso político, confiança e justificativa.
- `data/sources/source-aliases.yml`: nomes alternativos que o Google News emite para a mesma fonte.
- `data/sources/methodology.md`: regras para revisar o posicionamento editorial.
- `data/sources/review-template.md`: modelo de sugestão para issues/PRs.

A escala mede linha editorial percebida, não veracidade/credibilidade: `1` = progressista forte, `5` = centro/institucional/sem viés nacional claro, `10` = conservador forte.

## Ideia de arquitetura

```text
GitHub Actions diário → scraper Google News → public/data/latest.json → GitHub Pages React
```
