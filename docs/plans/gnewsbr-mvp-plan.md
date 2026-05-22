# GNewsBR MVP Plan

> Plano implementado inicialmente como protótipo visual. Sem backend no MVP.

## Objetivo

Criar um web app brasileiro estilo Ground News usando os stories/clusters do Google News Brasil como agrupamento inicial.

## Código de referência incorporado

- `get_manchete_raw()` descobre IDs de stories na home do Google News.
- `STORIES_URL_TEMPLATE` monta URLs `/stories/{id}`.
- `parse_google_news_data()` extrai dados de `AF_initDataCallback`.
- `process_parsed_data()` normaliza `title`, `description`, `time`, `url`, `posted`, `source`.
- `get_topic()` gera tópico por palavras frequentes.
- `news_political_spectrum` vira `data_sources/sources.br.json` na próxima fase.
- `get_link_preview()` vira enriquecimento opcional para imagem/descrição/domínio.

## Fases

1. UI React estática com dados mockados no schema final.
2. Migrar dicionário de espectro para JSON.
3. Refatorar scraper Python em pacote com testes e export JSON.
4. GitHub Actions diário.
5. Deploy GitHub Pages.

## Cuidados

- Classificação exibida como “perfil editorial estimado”.
- Não republicar corpo completo das matérias.
- Manter `latest.json` anterior se o scraper falhar.
