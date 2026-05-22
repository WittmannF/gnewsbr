# GNewsBR

Web app brasileiro inspirado no Ground News. O MVP usa clusters/stories do Google News Brasil como agrupamento inicial, aplica metadados editoriais manuais por fonte e exibe comparação de cobertura em uma UI React responsiva.

## Status

Protótipo visual local com dados reais coletados do Google News Brasil. A coleta atual descobre stories a partir de **Manchetes/Home + tópicos encontrados no menu do Google News**, abre cada `/stories/<id>` e gera `public/data/latest.json` com título, resumo, fonte, link, horário e distribuição editorial estimada.

Na última coleta local: **347 stories encontrados/coletados** e **5.937 artigos relacionados**.

## Comandos

```bash
npm install
npm run collect  # gera public/data/latest.json
npm run dev -- --host 0.0.0.0 --port 4177
npm run build
npm run preview -- --host 0.0.0.0 --port 4177
```

## Ideia de arquitetura

```text
GitHub Actions diário → scraper Google News → public/data/latest.json → GitHub Pages React
```
