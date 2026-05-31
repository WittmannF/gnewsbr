import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { ArrowLeft, BarChart3, CalendarClock, CheckCircle2, Download, ExternalLink, Filter, Gauge, Code2, Newspaper, Search, ShieldQuestion, Sparkles, TrendingUp, WifiOff } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { bucketColors, bucketLabels, mockNewsData } from './data'
import type { Cluster, ClusterDetail, NewsPayload, SpectrumBucket } from './types'

const bucketOrder: SpectrumBucket[] = ['left', 'centerLeft', 'center', 'centerRight', 'right', 'unknown']
const validViews = ['home', 'sources', 'methodology'] as const
type AppView = (typeof validViews)[number]
type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}
const FALLBACK_CLUSTER_IMAGE = 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=1200&q=80'

function onImageError(event: React.SyntheticEvent<HTMLImageElement>) {
  const img = event.currentTarget
  if (img.src === FALLBACK_CLUSTER_IMAGE) {
    return
  }
  img.src = FALLBACK_CLUSTER_IMAGE
}

function SpectrumBar({ cluster, compact = false }: { cluster: Cluster; compact?: boolean }) {
  const total = Math.max(1, Object.values(cluster.spectrum.buckets).reduce((a, b) => a + b, 0))
  return (
    <div className="spectrum">
      <div className="spectrum-track" aria-label="Distribuição editorial estimada">
        {bucketOrder.map((bucket) => {
          const count = cluster.spectrum.buckets[bucket]
          if (!count) return null
          return <span key={bucket} className="spectrum-segment" title={`${bucketLabels[bucket]}: ${count}`} style={{ width: `${(count / total) * 100}%`, background: bucketColors[bucket] }} />
        })}
      </div>
      {!compact && (
        <div className="spectrum-legend">
          {bucketOrder.map((bucket) => cluster.spectrum.buckets[bucket] ? (
            <span key={bucket}><i style={{ background: bucketColors[bucket] }} />{bucketLabels[bucket]} · {cluster.spectrum.buckets[bucket]}</span>
          ) : null)}
        </div>
      )}
    </div>
  )
}

function ScorePill({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof Gauge }) {
  return <div className="score-pill"><Icon size={16} /><span>{label}</span><strong>{value}</strong></div>
}

function ClusterCard({ cluster, onOpen }: { cluster: Cluster; onOpen: (cluster: Cluster) => void }) {
  const sourceNames = cluster.topSources ?? Array.from(new Set((cluster.articles ?? []).map((a) => a.source))).slice(0, 5)
  const articleCount = cluster.articleCount ?? (cluster.articles?.length ?? 0)
  const imageSrc = cluster.imageUrl || FALLBACK_CLUSTER_IMAGE
  return (
    <article className="cluster-card" onClick={() => onOpen(cluster)}>
      <div className="cluster-image">
        <img src={imageSrc} alt="" loading="lazy" referrerPolicy="no-referrer" onError={onImageError} />
        <span>{cluster.topic}</span>
      </div>
      <div className="cluster-body">
        <div className="cluster-meta"><span>{articleCount} artigos</span><span>{cluster.spectrum.knownCount} fontes classificadas</span></div>
        <h2>{cluster.title}</h2>
        <p>{cluster.summary}</p>
        <SpectrumBar cluster={cluster} compact />
        <div className="flag-row">{cluster.flags.slice(0, 3).map((flag) => <span key={flag}>{flag}</span>)}</div>
        <div className="card-footer">
          <div className="source-stack">{sourceNames.map((s) => <b key={s}>{s.slice(0, 2).toUpperCase()}</b>)}</div>
          <button>Comparar cobertura <ExternalLink size={14} /></button>
        </div>
      </div>
    </article>
  )
}

function Header({ current, onNavigate }: { current: string; onNavigate: (view: string) => void }) {
  return (
    <header className="topbar">
      <button className="brand" onClick={() => onNavigate('home')}>
        <span className="brand-mark"><Newspaper size={20} /></span>
        <span><strong>GNewsBR</strong><small>Brasil em perspectiva</small></span>
      </button>
      <nav>
        {['home', 'sources', 'methodology'].map((item) => (
          <button key={item} className={current === item ? 'active' : ''} onClick={() => onNavigate(item)}>
            {item === 'home' ? 'Hoje' : item === 'sources' ? 'Fontes' : 'Metodologia'}
          </button>
        ))}
      </nav>
      <a className="github-link" href="https://github.com/WittmannF/gnewsbr" target="_blank"><Code2 size={16} /> GitHub</a>
    </header>
  )
}

function HomePage({ data, onOpen, onNavigate }: { data: NewsPayload; onOpen: (cluster: Cluster) => void; onNavigate: (view: string) => void }) {
  const [query, setQuery] = useState('')
  const [topic, setTopic] = useState('Todos')
  const topics = useMemo(() => {
    const counts = new Map<string, number>()
    data.clusters.forEach((cluster) => {
      const key = cluster.topic.split(' · ')[0]
      counts.set(key, (counts.get(key) ?? 0) + 1)
    })
    const ranked = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 18)
      .map(([name]) => name)
    return ['Todos', ...ranked]
  }, [data.clusters])
  const hiddenTopicCount = Math.max(0, new Set(data.clusters.map((c) => c.topic.split(' · ')[0])).size - (topics.length - 1))
  const filtered = useMemo(() => data.clusters.filter((cluster) => {
    const q = query.trim().toLowerCase()
    const searchSources = cluster.topSources ?? (cluster.articles ?? []).map((a) => a.source)
    const matchesQuery = !q || [cluster.title, cluster.summary, cluster.topic, ...cluster.topicKeywords, ...searchSources].join(' ').toLowerCase().includes(q)
    const matchesTopic = topic === 'Todos' || cluster.topic.includes(topic)
    return matchesQuery && matchesTopic
  }), [data.clusters, query, topic])

  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow"><Sparkles size={16} /> Radar de cobertura da imprensa brasileira</span>
          <h1>Compare como a imprensa brasileira cobre a mesma história.</h1>
          <p>Um radar editorial com clusters, manchetes lado a lado, distribuição estimada de perfis e links para as fontes originais.</p>
          <div className="hero-actions"><button onClick={() => document.getElementById('clusters')?.scrollIntoView({ behavior: 'smooth' })}>Ver notícias de hoje</button><button className="secondary" onClick={() => onNavigate('methodology')}>Como funciona</button></div>
        </div>
        <div className="hero-panel">
          <div className="panel-title"><BarChart3 /> Snapshot da coleta</div>
          <div className="kpi-grid">
            <ScorePill label="Stories" value={data.stats.clusterCount} icon={Newspaper} />
            <ScorePill label="Artigos" value={data.stats.articleCount} icon={TrendingUp} />
            <ScorePill label="Fontes" value={data.stats.knownSources} icon={CheckCircle2} />
            <ScorePill label="Atualizado" value={formatDistanceToNow(new Date(data.generatedAt), { addSuffix: true, locale: ptBR })} icon={CalendarClock} />
          </div>
          <div className="method-note"><ShieldQuestion size={16} /> Classificação editorial manual inicial — exibida como estimativa, não como verdade absoluta.</div>
        </div>
      </section>

      <section className="toolbar" id="clusters">
        <div className="search-box"><Search size={18} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar tema, fonte ou palavra-chave" /></div>
        <div className="topic-tabs"><Filter size={16} />{topics.map((t) => <button key={t} className={topic === t ? 'active' : ''} onClick={() => setTopic(t)}>{t}</button>)}{hiddenTopicCount > 0 ? <span className="topic-hint">+{hiddenTopicCount} temas via busca</span> : null}</div>
      </section>

      <section className="cluster-grid">
        {filtered.map((cluster) => <ClusterCard key={cluster.id} cluster={cluster} onOpen={onOpen} />)}
      </section>
    </main>
  )
}

function ClusterDetail({ cluster, loading, error, onRetry, onBack }: { cluster: ClusterDetail | null; loading: boolean; error: string | null; onRetry: () => void; onBack: () => void }) {
  if (loading) {
    return (
      <main className="detail-page">
        <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Voltar</button>
        <section className="plain-page"><h1>Carregando cobertura</h1><p>Buscando os artigos completos deste cluster.</p></section>
      </main>
    )
  }

  if (error || !cluster) {
    return (
      <main className="detail-page">
        <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Voltar</button>
        <section className="plain-page"><h1>Falha ao carregar detalhe</h1><p>{error ?? 'Detalhe indisponivel no momento.'}</p><button onClick={onRetry}>Tentar novamente</button></section>
      </main>
    )
  }

  const byBucket = bucketOrder.map((bucket) => ({ bucket, articles: cluster.articles.filter((a) => a.bucket === bucket) })).filter((g) => g.articles.length)
  return (
    <main className="detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Voltar</button>
      <section className="detail-hero">
        <div>
          <span className="eyebrow">{cluster.topic}</span>
          <h1>{cluster.title}</h1>
          <p>{cluster.summary}</p>
          <div className="flag-row large">{cluster.flags.map((flag) => <span key={flag}>{flag}</span>)}</div>
        </div>
        <img src={cluster.imageUrl || FALLBACK_CLUSTER_IMAGE} alt="" referrerPolicy="no-referrer" onError={onImageError} />
      </section>
      <section className="analysis-grid">
        <div className="analysis-card wide"><h3>Distribuição editorial estimada</h3><SpectrumBar cluster={cluster} /><div className="metric-row"><ScorePill label="Média" value={cluster.spectrum.average?.toFixed(1) ?? '—'} icon={Gauge} /><ScorePill label="Amplitude" value={`${cluster.spectrum.min ?? '—'}–${cluster.spectrum.max ?? '—'}`} icon={BarChart3} /><ScorePill label="Divergência" value={`${cluster.scores.headlineDivergence}%`} icon={TrendingUp} /></div></div>
        <div className="analysis-card"><h3>Confiança do cluster</h3><div className="radial"><span>{cluster.scores.confidence}%</span></div><p>Baseado em fontes conhecidas, quantidade de artigos e completude de metadados.</p></div>
      </section>
      <section className="headline-section">
        <h2>Manchetes por perfil</h2>
        <div className="headline-columns">
          {byBucket.map(({ bucket, articles }) => <div className="headline-col" key={bucket}><h3 style={{ color: bucketColors[bucket] }}>{bucketLabels[bucket]}</h3>{articles.map((article) => <a href={article.url} key={article.id}><strong>{article.source}</strong><span>{article.title}</span><small>{article.postedLabel}</small></a>)}</div>)}
        </div>
      </section>
    </main>
  )
}

function formatPoliticalWeight(weight?: number) {
  if (weight === undefined || Number.isNaN(weight)) return '—'
  const normalized = Math.max(1, Math.min(5, weight <= 1 ? weight * 5 : weight))
  return Number.isInteger(normalized) ? String(normalized) : normalized.toFixed(1)
}

function SourcesPage({ data }: { data: NewsPayload }) {
  const [query, setQuery] = useState('')
  const [bucket, setBucket] = useState<SpectrumBucket | 'all'>('all')
  const [status, setStatus] = useState<'all' | 'reviewed' | 'draft' | 'disputed'>('all')

  const sourceCoverage = useMemo(() => {
    const coverage = new Map<string, { articles: number; clusters: number }>()
    data.sources.forEach((source) => {
      const current = coverage.get(source.name) ?? { articles: 0, clusters: 0 }
      if (source.coverage) {
        current.articles = source.coverage.articles
        current.clusters = source.coverage.clusters
      }
      coverage.set(source.name, current)
    })

    data.clusters.forEach((cluster) => {
      const seenSources = new Set<string>()
      ;(cluster.articles ?? []).forEach((article) => {
        const key = article.sourceCanonical || article.source
        const current = coverage.get(key) ?? { articles: 0, clusters: 0 }
        current.articles += 1
        if (!seenSources.has(key)) {
          current.clusters += 1
          seenSources.add(key)
        }
        coverage.set(key, current)
      })
    })
    return coverage
  }, [data.clusters, data.sources])

  const bucketCounts = useMemo(() => bucketOrder
    .filter((item) => item !== 'unknown')
    .map((item) => ({ bucket: item, count: data.sources.filter((source) => source.bucket === item).length })), [data.sources])
  const reviewedCount = data.sources.filter((source) => source.reviewStatus === 'reviewed').length
  const filteredSources = useMemo(() => data.sources.filter((source) => {
    const q = query.trim().toLowerCase()
    const coverage = sourceCoverage.get(source.name)
    const haystack = [source.name, source.label, source.type, source.scope, source.region, source.rationale, ...(source.notes ?? [])].join(' ').toLowerCase()
    const matchesQuery = !q || haystack.includes(q)
    const matchesBucket = bucket === 'all' || source.bucket === bucket
    const matchesStatus = status === 'all' || source.reviewStatus === status
    return matchesQuery && matchesBucket && matchesStatus && (coverage || !q)
  }), [bucket, data.sources, query, sourceCoverage, status])

  return (
    <main className="plain-page sources-page">
      <section className="sources-hero">
        <div>
          <span className="eyebrow"><ShieldQuestion size={16} /> Mapa editorial auditável</span>
          <h1>Fontes monitoradas</h1>
          <p>Consulte a classificação editorial usada no radar, a confiança da revisão e a presença de cada veículo na coleta atual. A escala é uma estimativa editorial revisável — não mede qualidade, verdade ou credibilidade.</p>
          <div className="ai-review-note"><Sparkles size={17} /><span>As revisões e justificativas desta rodada foram <strong>assistidas por IA</strong> e devem ser tratadas como rascunho auditável até validação editorial humana.</span></div>
        </div>
        <div className="source-summary-grid">
          <ScorePill label="Fontes no mapa" value={data.sources.length} icon={Newspaper} />
          <ScorePill label="Revisadas" value={reviewedCount} icon={CheckCircle2} />
          <ScorePill label="Na coleta" value={data.stats.knownSources} icon={TrendingUp} />
          <ScorePill label="Sem mapa" value={data.stats.unknownSources} icon={ShieldQuestion} />
        </div>
      </section>

      <section className="source-spectrum-panel">
        <div className="panel-title"><BarChart3 /> Distribuição do mapa de fontes</div>
        <div className="source-bucket-bars">
          {bucketCounts.map(({ bucket: item, count }) => {
            const percent = Math.round((count / Math.max(1, data.sources.length)) * 100)
            return <button key={item} className={bucket === item ? 'active' : ''} onClick={() => setBucket(bucket === item ? 'all' : item)}><span><i style={{ background: bucketColors[item] }} />{bucketLabels[item]}</span><strong>{count}</strong><em style={{ width: `${percent}%`, background: bucketColors[item] }} /></button>
          })}
        </div>
      </section>

      <section className="metric-guide">
        <div className="panel-title"><Gauge /> Como ler as métricas</div>
        <div className="metric-guide-grid">
          <div><strong>Score editorial</strong><p>Escala 1–10 usada para posicionar fontes no espectro: valores menores indicam perfil mais progressista; valores maiores, mais conservador; o centro fica próximo de 5–6.</p></div>
          <div><strong>Peso político</strong><p>Indicador exibido em escala 1–5, convertido do peso relativo interno 0–1. Ajuda a estimar influência no debate político nacional combinando alcance, frequência em Brasília/eleições e relevância para formadores de opinião.</p></div>
          <div><strong>Confiança</strong><p>Mostra quão segura é a classificação atual. “Alta” indica fonte conhecida e metadados consistentes; “média/baixa” pede revisão humana.</p></div>
          <div><strong>Presença na coleta</strong><p>Conta quantos artigos e clusters daquele veículo apareceram no snapshot atual da coleta, sem representar audiência total.</p></div>
        </div>
      </section>

      <section className="sources-toolbar">
        <div className="search-box"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por veículo, justificativa, tipo ou país" /></div>
        <div className="topic-tabs"><Filter size={16} /><button className={bucket === 'all' ? 'active' : ''} onClick={() => setBucket('all')}>Todos os perfis</button>{bucketOrder.filter((item) => item !== 'unknown').map((item) => <button key={item} className={bucket === item ? 'active' : ''} onClick={() => setBucket(item)}>{bucketLabels[item]}</button>)}</div>
        <div className="topic-tabs compact"><button className={status === 'all' ? 'active' : ''} onClick={() => setStatus('all')}>Todos</button><button className={status === 'reviewed' ? 'active' : ''} onClick={() => setStatus('reviewed')}>Revisadas</button><button className={status === 'draft' ? 'active' : ''} onClick={() => setStatus('draft')}>Rascunho</button><button className={status === 'disputed' ? 'active' : ''} onClick={() => setStatus('disputed')}>Disputadas</button></div>
      </section>

      <div className="source-results"><strong>{filteredSources.length}</strong> fontes exibidas · ordenadas por presença na coleta e score editorial</div>
      <div className="source-grid enhanced">
        {filteredSources
          .slice()
          .sort((a, b) => (sourceCoverage.get(b.name)?.articles ?? 0) - (sourceCoverage.get(a.name)?.articles ?? 0) || (a.spectrumScore ?? 99) - (b.spectrumScore ?? 99) || a.name.localeCompare(b.name))
          .map((source) => {
            const coverage = sourceCoverage.get(source.name)
            return <article className="source-card enhanced" key={source.name}>
              <div className="source-card-head"><div><strong>{source.name}</strong><span>{source.scope ?? source.region} · {source.type}</span></div><b style={{ color: bucketColors[source.bucket] }}>{source.spectrumScore ?? '—'}</b></div>
              <div className="source-label-row"><span style={{ borderColor: bucketColors[source.bucket], color: bucketColors[source.bucket] }}>{source.label}</span><small>{source.reviewStatus === 'reviewed' ? 'Revisada com IA' : source.reviewStatus === 'disputed' ? 'Disputada' : 'Rascunho IA'} · confiança {source.confidence}</small></div>
              <p>{source.rationale ?? 'Classificação inicial assistida por IA e aberta para revisão editorial humana.'}</p>
              {source.notes?.length ? <ul>{source.notes.slice(0, 2).map((note) => <li key={note}>{note}</li>)}</ul> : null}
              <div className="source-foot"><span>{coverage?.articles ?? 0} artigos nesta coleta</span><span>{coverage?.clusters ?? 0} clusters</span><span>peso político {formatPoliticalWeight(source.politicalWeight)}</span></div>
            </article>
          })}
      </div>
    </main>
  )
}

function MethodologyPage() {
  return <main className="plain-page"><h1>Metodologia</h1><div className="methodology"><section><h2>1. Coleta</h2><p>A rotina de coleta identifica histórias em alta, agrupa URLs relacionadas e preserva metadados mínimos para comparação: título, snippet, veículo, horário e link original.</p></section><section><h2>2. Clusters</h2><p>O agrupamento reúne diferentes veículos cobrindo a mesma história. Isso permite comparar enquadramentos, diversidade de fontes e distribuição editorial em uma experiência única.</p></section><section><h2>3. Espectro editorial</h2><p>A escala 1–10 posiciona fontes em rótulos cuidadosos: progressista, centro-progressista, centro, centro-conservador e conservador. As revisões assistidas por IA permanecem auditáveis.</p></section><section><h2>4. Limitações</h2><p>Não republicamos conteúdo completo; mostramos título, snippet, fonte e link. A classificação não mede verdade/falsidade e deve ser auditável.</p></section></div></main>
}

function PwaStatus({
  isOffline,
  canInstall,
  needRefresh,
  onInstall,
  onRefresh,
  onDismissUpdate,
}: {
  isOffline: boolean
  canInstall: boolean
  needRefresh: boolean
  onInstall: () => void
  onRefresh: () => void
  onDismissUpdate: () => void
}) {
  if (!isOffline && !canInstall && !needRefresh) {
    return null
  }

  return (
    <aside className="pwa-toast" aria-live="polite">
      {isOffline ? (
        <div className="pwa-toast-row offline"><WifiOff size={17} /><span>Você está offline. Mostrando a última atualização salva quando disponível.</span></div>
      ) : null}
      {needRefresh ? (
        <div className="pwa-toast-row"><Sparkles size={17} /><span>Nova versão disponível.</span><button onClick={onRefresh}>Atualizar agora</button><button className="ghost" onClick={onDismissUpdate}>Depois</button></div>
      ) : null}
      {canInstall ? (
        <div className="pwa-toast-row"><Download size={17} /><span>Instalar app para abrir o GNewsBR em tela cheia.</span><button onClick={onInstall}>Instalar app</button><small>iOS: use Compartilhar → Adicionar à Tela de Início.</small></div>
      ) : null}
    </aside>
  )
}

export function App() {
  const [view, setView] = useState<AppView>('home')
  const [data, setData] = useState<NewsPayload>(mockNewsData)
  const [selected, setSelected] = useState<Cluster | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<ClusterDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [isOffline, setIsOffline] = useState(() => typeof navigator !== 'undefined' ? !navigator.onLine : false)
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(registration) {
      registration?.update()
    },
    onRegisterError(error) {
      console.warn('Falha ao registrar service worker do GNewsBR', error)
    },
  })

  const routeFromUrl = useCallback((): { view: AppView; clusterId: string | null } => {
    const params = new URLSearchParams(window.location.search)
    const maybeView = params.get('view')
    const nextView = validViews.includes(maybeView as AppView) ? (maybeView as AppView) : 'home'
    const clusterId = params.get('cluster')
    return { view: nextView, clusterId }
  }, [])

  const updateUrl = useCallback((nextView: AppView, clusterId: string | null, mode: 'push' | 'replace' = 'push') => {
    const params = new URLSearchParams()
    if (nextView !== 'home') {
      params.set('view', nextView)
    }
    if (clusterId) {
      params.set('cluster', clusterId)
    }
    const query = params.toString()
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname
    if (mode === 'replace') {
      window.history.replaceState({ view: nextView, clusterId }, '', nextUrl)
      return
    }
    window.history.pushState({ view: nextView, clusterId }, '', nextUrl)
  }, [])

  const clearDetailState = useCallback(() => {
    setSelected(null)
    setSelectedDetail(null)
    setDetailError(null)
    setDetailLoading(false)
  }, [])

  useEffect(() => {
    const updateOnlineState = () => setIsOffline(!navigator.onLine)
    const captureInstallPrompt = (event: Event) => {
      event.preventDefault()
      setInstallPrompt(event as BeforeInstallPromptEvent)
    }

    window.addEventListener('online', updateOnlineState)
    window.addEventListener('offline', updateOnlineState)
    window.addEventListener('beforeinstallprompt', captureInstallPrompt)
    return () => {
      window.removeEventListener('online', updateOnlineState)
      window.removeEventListener('offline', updateOnlineState)
      window.removeEventListener('beforeinstallprompt', captureInstallPrompt)
    }
  }, [])

  const installApp = useCallback(async () => {
    if (!installPrompt) {
      return
    }
    await installPrompt.prompt()
    const choice = await installPrompt.userChoice
    if (choice.outcome !== 'dismissed') {
      setInstallPrompt(null)
    }
  }, [installPrompt])

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/latest.json`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((payload: NewsPayload) => setData(payload))
      .catch(() => setData(mockNewsData))
  }, [])

  const loadClusterDetail = useCallback((summary: Cluster, updateHistory = true) => {
    setView('home')
    setSelected(summary)
    setDetailLoading(true)
    setDetailError(null)
    setSelectedDetail(null)

    if (updateHistory) {
      updateUrl('home', summary.id, 'push')
    }

    if (summary.articles?.length) {
      const legacyDetail: ClusterDetail = {
        ...summary,
        articles: summary.articles,
      }
      setSelectedDetail(legacyDetail)
      setDetailLoading(false)
      return
    }

    if (!summary.detailPath) {
      setDetailError('Detalhe deste cluster nao esta disponivel neste snapshot.')
      setDetailLoading(false)
      return
    }

    fetch(`${import.meta.env.BASE_URL}${summary.detailPath}`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((detail: ClusterDetail) => {
        if (!detail.articles) {
          throw new Error('Detalhe sem artigos')
        }
        setSelectedDetail(detail)
      })
      .catch((error: Error) => {
        setDetailError(`Nao foi possivel carregar os detalhes (${error.message}).`)
      })
      .finally(() => setDetailLoading(false))
  }, [updateUrl])

  useEffect(() => {
    const syncRouteFromUrl = () => {
      const { view: routeView, clusterId } = routeFromUrl()
      setView(routeView)

      if (!clusterId) {
        clearDetailState()
        return
      }

      const summary = data.clusters.find((cluster) => cluster.id === clusterId)
      if (!summary) {
        clearDetailState()
        return
      }

      if (selected?.id === clusterId) {
        return
      }

      loadClusterDetail(summary, false)
    }

    syncRouteFromUrl()
    window.addEventListener('popstate', syncRouteFromUrl)
    return () => window.removeEventListener('popstate', syncRouteFromUrl)
  }, [clearDetailState, data.clusters, loadClusterDetail, routeFromUrl, selected?.id])

  const navigate = (next: string) => {
    if (!validViews.includes(next as AppView)) {
      return
    }
    const nextView = next as AppView
    const currentRoute = routeFromUrl()
    if (currentRoute.view === nextView && !currentRoute.clusterId) {
      return
    }

    clearDetailState()
    setView(nextView)
    updateUrl(nextView, null, 'push')
  }

  const closeDetail = () => {
    const { clusterId } = routeFromUrl()
    if (clusterId) {
      window.history.back()
      return
    }
    updateUrl(view, null, 'replace')
    clearDetailState()
  }

  const retryDetail = () => {
    if (selected) {
      loadClusterDetail(selected, false)
    }
  }

  return <><Header current={selected ? 'home' : view} onNavigate={navigate} /><PwaStatus isOffline={isOffline} canInstall={Boolean(installPrompt)} needRefresh={needRefresh} onInstall={installApp} onRefresh={() => updateServiceWorker(true)} onDismissUpdate={() => setNeedRefresh(false)} />{selected ? <ClusterDetail cluster={selectedDetail} loading={detailLoading} error={detailError} onRetry={retryDetail} onBack={closeDetail} /> : view === 'sources' ? <SourcesPage data={data} /> : view === 'methodology' ? <MethodologyPage /> : <HomePage data={data} onOpen={loadClusterDetail} onNavigate={navigate} />}</>
}
