# PWA do GNewsBR

Este PR transforma o GNewsBR em Progressive Web App instalável, mantendo o escopo conservador para um site estático em GitHub Pages.

## Instalação

### Android / Chrome

1. Abrir o GNewsBR no Chrome.
2. Aguardar o CTA `Instalar app` no rodapé da interface ou usar o menu do navegador.
3. Confirmar a instalação. O app abre em modo `standalone`, sem barra do navegador.

O CTA usa o evento `beforeinstallprompt` e só aparece quando o navegador considera a página instalável.

### iOS / Safari

O iOS não expõe `beforeinstallprompt`. A instrução exibida na interface é manual:

1. Abrir o GNewsBR no Safari.
2. Tocar em Compartilhar.
3. Escolher `Adicionar à Tela de Início`.

## Estratégia de cache

A configuração está em `vite.config.ts`, via `vite-plugin-pwa` + Workbox.

- Shell da aplicação: pré-cache gerado pelo build do Vite.
- `data/latest.json`: `NetworkFirst`, com timeout curto, para priorizar a coleta mais recente e cair para cache quando estiver offline ou em rede ruim.
- Detalhes de clusters `data/archive/YYYY-MM-DD/story_*.json`: `StaleWhileRevalidate`, para abrir rápido o detalhe já visto e atualizar em segundo plano.
- Arquivo histórico em `data/archive/`: `CacheFirst`, porque snapshots antigos são essencialmente imutáveis.
- Imagens remotas do Unsplash: `CacheFirst` limitado, para melhorar reabertura visual sem inflar cache indefinidamente.

## Experiência offline

Quando `navigator.onLine` indica queda de rede, o app mostra o aviso:

> Você está offline. Mostrando a última atualização salva quando disponível.

Se `latest.json` ou um detalhe de cluster já estiverem no cache do service worker, a experiência continua funcionando. Se não houver cache, o app mantém o fallback local já existente (`mockNewsData`) e exibe o erro de detalhe com botão de retry.

## Atualização de versão

O registro do service worker usa `registerType: 'prompt'`. Quando há nova versão disponível, a UI mostra `Nova versão disponível` com:

- `Atualizar agora`: ativa `updateServiceWorker(true)` e recarrega para a versão nova.
- `Depois`: descarta o aviso atual, sem forçar reload.

## Validação

Com Node disponível:

```bash
npm install
npm run pwa:validate
npm run build
```

O teste `tests/validate_pwa.py` valida presença do plugin, manifest, estratégias de cache, metadados mobile, ícones e UX de instalação/offline/update.
