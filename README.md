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


## Leitura diária e ranking

- **Hoje:** radar de cobertura, mantendo a ordem atual por quantidade de artigos e fontes classificadas; a síntese por IA não muda a posição.
- **Edição:** clusters sintetizados agrupados por data (horário de Brasília), com foto, resumo e comparação de cobertura quando os metadados originais estiverem disponíveis. O índice de notícias passa a guardar um snapshot do cluster e os links das fontes na publicação: uma coleta horária posterior não apaga a comparação. Quando apenas os metadados de extração sobreviveram, a comparação usa esses dados, sem inventar imagem nem métricas; quando nenhum snapshot existir, as fontes originais continuam clicáveis. A notícia IA e a comparação usam os JSONs existentes, sem outra chamada ao LLM nem banco de dados.
- **Top 15 da home:** o arquivamento diário agora prioriza as 15 primeiras histórias do snapshot utilizado; a síntese prioriza os mesmos IDs e, se houver espaço, inclui outros clusters. O ranking não é modificado. O número efetivamente sintetizado pode ser inferior a 15 quando o extrator não conseguir duas fontes úteis, houver falha de API ou orçamento esgotado; a home exibe a cobertura real. Como a coleta da home é horária e a síntese diária, a cobertura das *15 atuais* pode variar entre execuções.

## Síntese multifonte experimental (issue #16)

A interface mantém os dados brutos de Google News como fallback. Quando um cluster tiver um resultado **válido** em `public/data/enrichment/news/{clusterId}.json`, a home apresenta uma manchete e um subtítulo próprios, e o detalhe mostra seções e links das fontes efetivamente consultadas. A síntese é assistida por IA, não substitui a leitura das matérias e não constitui verificação factual independente.

### Configuração

1. Gere uma chave em https://openrouter.ai/settings/keys.
2. Cadastre `OPENROUTER_API_KEY` em **Repository Settings > Secrets and variables > Actions** (não em `VITE_*`, `public/` ou arquivo versionado).
3. Opcionalmente configure `OPENROUTER_MODEL` em **Actions Variables**; padrão: `z-ai/glm-5.3-flash`.
4. Execute **Actions > Generate grounded news syntheses > Run workflow** com `max_clusters=3` antes de habilitar o fluxo normal. A geração paga agendada e o bootstrap de sínteses no deploy Pages ficam **desativados por padrão**. Para ativá-los explicitamente, configure a Actions Variable `ENABLE_GNEWSBR_SYNTHESIS=true` (o secret sozinho não ativa chamadas pagas). A execução manual (`workflow_dispatch`) permanece disponível para testes deliberados. Os limites normais são até 20 clusters novos/dia, US$ 0,25/dia e US$ 5/mês em reservas estimadas. A coleta horária e o deploy Pages continuam funcionando sem a variável.

### Uso local

```bash
python -m pip install -r requirements.txt
export OPENROUTER_API_KEY='...'  # apenas na sua sessão; nunca commitar
python scripts/generate_news_synthesis.py --date YYYY-MM-DD --max-clusters 3 --dry-run
python scripts/generate_news_synthesis.py --date YYYY-MM-DD --max-clusters 3 --disable-jev
python -m unittest discover -s tests -p 'test_news_synthesis.py'
npm ci && npm run build
```

A execução usa `public/data/article-content/{date}/articles/` como entrada, aplica normalização e seleciona até cinco matérias válidas de domínios distintos por cluster. Não gera síntese com menos de duas fontes. A API solicita JSON Schema estrito e valida o resultado com Pydantic. Cada afirmação deve apontar para um artigo selecionado, com ID e URL válidos; o MVP não exige reproduzir excerpts literais. Resultados inválidos não são publicados, e nenhuma resposta mock entra no novo índice. A fonte original e seu link são preservados.

O detector de mudanças Jev (`typesafe/jev-1.14`) existe, mas o workflow **desabilita atualizações automáticas via Jev** até haver necessidade real de atualizá-las durante o dia. O MVP usa uma única chamada do GLM por história, sem tentativa adicional apenas para corrigir uma citação literal.

### Limites de custo (conservadores)

- 20 histórias novas por dia;
- 5 atualizações por dia e duas por história/dia;
- 12 horas entre atualizações ordinárias e 6 horas entre verificações semânticas por história;
- teto de reserva de US$ 0,25 por dia e US$ 5 por mês, registrados em `data/enrichment/cost-ledger/`.

O teto controla **estimativas de custo reservadas por execução**, não limites financeiros garantidos pelo provedor. Configure também limites de gasto no OpenRouter. Falhas de rede, restrições do modelo, paywall ou insuficiência de evidências mantêm a UI original.

### Segurança e limitações

O pipeline não envia a chave ao navegador. O passo de limpeza do artefato do Pages remove `dist/data/article-content/` para não publicar os textos completos extraídos. **Os arquivos históricos ainda versionados em `public/data/article-content/` permanecem acessíveis no próprio repositório público**: migrar esse armazenamento para artefatos privados com retenção limitada continua necessário. Não contornar paywalls e não republicar conteúdos originais.

Os artigos e a síntese são tratados como material potencialmente não confiável; validação de schema, citação e substring não garante que uma afirmação é factualmente verdadeira. É necessária revisão humana dos primeiros lotes antes de considerar o sistema apto à publicação regular.
