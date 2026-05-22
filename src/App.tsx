import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, BarChart3, CalendarClock, CheckCircle2, ExternalLink, Filter, Gauge, Code2, Newspaper, Search, ShieldQuestion, Sparkles, TrendingUp } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import { bucketColors, bucketLabels, mockNewsData } from './data'
import type { Cluster, NewsPayload, SpectrumBucket } from './types'

const bucketOrder: SpectrumBucket[] = ['left', 'centerLeft', 'center', 'centerRight', 'right', 'unknown']

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
  const sourceNames = Array.from(new Set(cluster.articles.map((a) => a.source))).slice(0, 5)
  return (
    <article className="cluster-card" onClick={() => onOpen(cluster)}>
      <div className="cluster-image" style={{ backgroundImage: `linear-gradient(180deg, rgba(8,12,24,.05), rgba(8,12,24,.72)), url(${cluster.imageUrl})` }}>
        <span>{cluster.topic}</span>
      </div>
      <div className="cluster-body">
        <div className="cluster-meta"><span>{cluster.articles.length} artigos</span><span>{cluster.spectrum.knownCount} fontes classificadas</span></div>
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

function HomePage({ data, onOpen }: { data: NewsPayload; onOpen: (cluster: Cluster) => void }) {
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
    const matchesQuery = !q || [cluster.title, cluster.summary, cluster.topic, ...cluster.topicKeywords, ...cluster.articles.map(a => a.source)].join(' ').toLowerCase().includes(q)
    const matchesTopic = topic === 'Todos' || cluster.topic.includes(topic)
    return matchesQuery && matchesTopic
  }), [data.clusters, query, topic])

  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow"><Sparkles size={16} /> MVP com clusters do Google News Brasil</span>
          <h1>Compare como a imprensa brasileira cobre a mesma história.</h1>
          <p>Um radar inspirado no Ground News: clusters, manchetes lado a lado, distribuição editorial estimada e links para as fontes originais.</p>
          <div className="hero-actions"><button onClick={() => document.getElementById('clusters')?.scrollIntoView({ behavior: 'smooth' })}>Ver notícias de hoje</button><button className="secondary">Como funciona</button></div>
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

function ClusterDetail({ cluster, onBack }: { cluster: Cluster; onBack: () => void }) {
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
        <img src={cluster.imageUrl} alt="" />
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

function SourcesPage({ data }: { data: NewsPayload }) {
  return <main className="plain-page"><h1>Fontes monitoradas</h1><p>O MVP começa com o dicionário manual do script de referência. A classificação é estimada e revisável.</p><div className="source-grid">{data.sources.map((source) => <div className="source-card" key={source.name}><div><strong>{source.name}</strong><span>{source.domain}</span></div><b style={{ color: bucketColors[source.bucket] }}>{source.spectrumScore ?? '—'}</b><small>{source.label} · {source.type} · {source.region}</small></div>)}</div></main>
}

function MethodologyPage() {
  return <main className="plain-page"><h1>Metodologia do MVP</h1><div className="methodology"><section><h2>1. Coleta</h2><p>O scraper usa a home do Google News Brasil para descobrir IDs de stories e abre cada URL <code>/stories/&lt;id&gt;</code>. O parser reaproveita a estrutura interna <code>AF_initDataCallback</code>, como no script de referência.</p></section><section><h2>2. Clusters</h2><p>No MVP, o agrupamento é herdado do Google News. Isso reduz complexidade e permite focar na experiência de comparação de cobertura.</p></section><section><h2>3. Espectro editorial</h2><p>A escala 1–10 do código original será migrada para JSON. Na UI pública, usamos rótulos cuidadosos: progressista, centro-progressista, centro, centro-conservador e conservador.</p></section><section><h2>4. Limitações</h2><p>Não republicamos conteúdo completo; mostramos título, snippet, fonte e link. A classificação não mede verdade/falsidade e deve ser auditável.</p></section></div></main>
}

export function App() {
  const [view, setView] = useState('home')
  const [data, setData] = useState<NewsPayload>(mockNewsData)
  const [selected, setSelected] = useState<Cluster | null>(null)

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/latest.json`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((payload: NewsPayload) => setData(payload))
      .catch(() => setData(mockNewsData))
  }, [])

  const navigate = (next: string) => { setSelected(null); setView(next) }
  return <><Header current={selected ? 'cluster' : view} onNavigate={navigate} />{selected ? <ClusterDetail cluster={selected} onBack={() => setSelected(null)} /> : view === 'sources' ? <SourcesPage data={data} /> : view === 'methodology' ? <MethodologyPage /> : <HomePage data={data} onOpen={setSelected} />}</>
}
