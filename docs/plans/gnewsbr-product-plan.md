# GNewsBR Product Plan

> Plano base do produto visual, com frontend estático e dados gerados por coleta editorial.

## Objetivo

Criar um web app brasileiro para comparar cobertura de imprensa a partir de stories/clusters de notícias relacionados.

## Código de referência incorporado

- `get_manchete_raw()` inspirou a descoberta inicial de IDs de stories.
- `STORIES_URL_TEMPLATE` monta URLs `/stories/{id}`.
- `parse_news_data()` virou parser de blobs `AF_initDataCallback`.
- `process_parsed_data()` normaliza `title`, `description`, `time`, `url`, `posted`, `source`.
- `get_topic()` gera tópico por palavras frequentes.
- `news_political_spectrum` foi migrado para configuração revisável em `data/sources/`.
- `get_link_preview()` vira enriquecimento opcional para imagem/descrição/domínio.

## Fases

1. UI React estática com dados no schema final.
2. Migrar dicionário de espectro para JSON/YAML revisável.
3. Refatorar scraper Python em pacote com testes e export JSON.
4. GitHub Actions diário.
5. Deploy GitHub Pages.

## Cuidados

- Classificação exibida como “perfil editorial estimado”.
- Não republicar corpo completo das matérias.
- Manter `latest.json` anterior se a coleta falhar.
