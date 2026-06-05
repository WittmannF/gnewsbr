# GNewsBR

Web app brasileiro para comparar como diferentes veículos cobrem a mesma história. O produto organiza clusters de cobertura, aplica metadados editoriais revisáveis por fonte e exibe a comparação em uma UI React responsiva.

## Status

Aplicação visual com dados reais de uma rotina de coleta editorial. A coleta atual descobre histórias em alta, agrupa links relacionados e gera um índice leve em `public/data/latest.json`, com detalhes completos por cluster em `public/data/clusters/latest/*.json`.

Na última coleta local: **347 stories encontrados/coletados** e **5.937 artigos relacionados**.

## Comandos

```bash
npm install
pip install -r requirements.txt
npm run sources:validate  # valida data/sources/source-spectrum.yml e aliases
npm run sources:build     # gera public/data/source-spectrum.json
npm run collect           # gera índice em public/data/latest.json + detalhes particionados
npm run articles:archive  # baixa texto limpo dos principais artigos em public/data/article-content/
npm run enrichment:daily  # gera enriquecimento/newsletter em public/data/enrichment/
npm run archive:migrate   # migra public/data/archive/*.json para pastas particionadas por dia
python3 scripts/image_preview_sandbox.py --clusters 2 --articles-per-cluster 4
npm run dev -- --host 0.0.0.0 --port 4177
npm run build
npm run preview -- --host 0.0.0.0 --port 4177
```

`npm run collect` tenta preencher imagens reais de preview a partir das metatags públicas das matérias (`og:image`/`twitter:image`). Use `-- --disable-preview-images` para pular essa etapa ou ajuste `--max-preview-image-fetches-per-story` e `--preview-image-timeout` ao rodar `scripts/generate_news_data.py` diretamente.

## Enriquecimento e newsletter diária

A camada de enriquecimento é aditiva e consome os textos limpos já arquivados por `npm run articles:archive` em `public/data/article-content/{YYYY-MM-DD}/`. Ela gera dados estruturados por cluster e uma newsletter diária sem alterar a coleta atual.

Exemplo local:

```bash
npm run articles:archive -- --date 2026-06-05 --max-clusters 2
npm run enrichment:daily -- --date 2026-06-05 --max-clusters 2
```

Saídas públicas:

- `public/data/enrichment/latest.json`
- `public/data/enrichment/latest.md`
- `public/data/enrichment/clusters/{clusterId}.json`
- `public/data/enrichment/newsletters/{YYYY-MM-DD}.json`
- `public/data/enrichment/newsletters/{YYYY-MM-DD}.md`

Por padrão, `enrichment:daily` usa `--llm-provider none` e gera um fallback determinístico/auditável com JSON validável. Para testar Ollama local:

```bash
LOCAL_LLM_MODEL=llama3.2:3b npm run enrichment:daily -- --date 2026-06-05 --llm-provider ollama --model llama3.2:3b
```

Os prompts versionados ficam em `scripts/enrichment/prompts/`. O workflow `.github/workflows/daily-enrichment.yml` pode rodar diariamente ou manualmente; o provider `none` mantém o CI barato, e `ollama` é opcional.

## Revisão colaborativa das fontes

A classificação editorial das fontes fica fora do código, em arquivos revisáveis por PR:

- `data/sources/source-spectrum.yml`: fonte canônica, score 1-10, tipo, peso político, confiança e justificativa.
- `data/sources/source-aliases.yml`: nomes alternativos emitidos pela coleta para a mesma fonte.
- `data/sources/methodology.md`: regras para revisar o posicionamento editorial.
- `data/sources/review-template.md`: modelo de sugestão para issues/PRs.

A escala mede linha editorial percebida, não veracidade/credibilidade: `1` = progressista forte, `5` = centro/institucional/sem viés nacional claro, `10` = conservador forte.

## Ideia de arquitetura

```text
GitHub Actions diário → coleta editorial → índice leve + detalhes particionados em public/data → GitHub Pages React

Formato de saída (particionado):

- `public/data/latest.json`: índice leve da coleta atual.
- `public/data/clusters/latest/{clusterId}.json`: detalhe completo de cada cluster atual.
- `public/data/archive/{YYYY-MM-DD}/index.json`: índice leve diário.
- `public/data/archive/{YYYY-MM-DD}/{clusterId}.json`: detalhe completo diário por cluster.
```
