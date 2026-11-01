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
npm run archive:migrate   # migra public/data/archive/*.json para pastas particionadas por dia
python3 scripts/image_preview_sandbox.py --clusters 2 --articles-per-cluster 4
npm run dev -- --host 0.0.0.0 --port 4177
npm run build
npm run preview -- --host 0.0.0.0 --port 4177
```

`npm run collect` tenta preencher imagens reais de preview a partir das metatags públicas das matérias (`og:image`/`twitter:image`). Use `-- --disable-preview-images` para pular essa etapa ou ajuste `--max-preview-image-fetches-per-story` e `--preview-image-timeout` ao rodar `scripts/generate_news_data.py` diretamente.

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


## Resumos de IA no top 15 (MVP)

A página **Hoje** conserva o ranking original (número de artigos e fontes classificadas).
A coleta horária produz `public/data/latest.json` e os detalhes dos clusters.
No mesmo workflow de publicação, `scripts/summarize_home.py` percorre os **15
primeiros IDs desse mesmo snapshot** e:

1. Reutiliza `public/data/enrichment/briefs/{clusterId}.json` quando existe;
2. Para um cluster novo com pelo menos duas fontes, envia até cinco manchetes e
   descrições ao GLM via OpenRouter, solicitando **somente um resumo curto**;
3. Adiciona `aiSummary` e `aiSources` ao índice e ao JSON de detalhe, para a
   home e a página de comparação exibirem o mesmo texto e os links reais;
4. Publica mesmo quando o LLM está indisponível: nessas situações, mantém o
   resumo original e informa os IDs não atendidos no log.

Não há regeneração de um resumo existente, extração integral obrigatória,
atualização semântica com Jev ou novo banco de dados. A aba **Edição** permanece
como acesso secundário às sínteses históricas já publicadas.

**Configuração:** `OPENROUTER_API_KEY` como secret de GitHub Actions; opcionalmente
`OPENROUTER_MODEL` como variável (padrão `z-ai/glm-5.3-flash`). A geração simples
fica habilitada por padrão e pode ser pausada com a variável
`ENABLE_GNEWSBR_SYNTHESIS=false`. A chave nunca chega ao cliente React.

**Custos:** reserva conservadora de US$ 0,01 por tentativa, com máximo de
US$ 0,25/dia e US$ 5/mês, compartilhando o ledger já existente em
`data/enrichment/cost-ledger/`. São reservas estimadas, não a fatura efetiva do
provedor. Configure um teto financeiro real também no OpenRouter.

**Testes locais:**

```bash
python -m unittest discover -s tests -p 'test_summarize_home.py'
python3 scripts/summarize_home.py --dry-run
npm run build
```

O antigo workflow de sínteses estruturadas e o arquivamento integral de artigos
continuam disponíveis **apenas manualmente**, sem agendamento redundante.
Os detalhes de clusters já publicados são preservados por 30 dias para que
índices ainda em cache no PWA não percam seus links.

### Segurança e limitações

O pipeline não envia a chave ao navegador. O passo de limpeza do artefato do Pages remove `dist/data/article-content/` para não publicar os textos completos extraídos. **Os arquivos históricos ainda versionados em `public/data/article-content/` permanecem acessíveis no próprio repositório público**: migrar esse armazenamento para artefatos privados com retenção limitada continua necessário. Não contornar paywalls e não republicar conteúdos originais.

Os artigos e a síntese são tratados como material potencialmente não confiável; validação de schema, citação e substring não garante que uma afirmação é factualmente verdadeira. É necessária revisão humana dos primeiros lotes antes de considerar o sistema apto à publicação regular.
