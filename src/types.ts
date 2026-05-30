export type SpectrumBucket = 'left' | 'centerLeft' | 'center' | 'centerRight' | 'right' | 'unknown'

export type SourceMeta = {
  name: string
  domain?: string
  spectrumScore?: number
  bucket: SpectrumBucket
  label: string
  confidence: 'manual' | 'inferred' | 'unknown' | 'low' | 'medium' | 'high'
  region: string
  type: string
  scope?: string
  politicalWeight?: number
  reviewStatus?: 'draft' | 'reviewed' | 'disputed'
  rationale?: string
  notes?: string[]
}

export type SourceCoverage = {
  articles: number
  clusters: number
}

export type IndexedSourceMeta = SourceMeta & {
  coverage?: SourceCoverage
}

export type Article = {
  id: string
  title: string
  description: string
  url: string
  source: string
  sourceCanonical?: string
  sourceDomain?: string
  publishedAt: string
  postedLabel: string
  imageUrl?: string
  spectrumScore?: number
  bucket: SpectrumBucket
}

export type Cluster = {
  id: string
  detailPath?: string
  storyUrl: string
  title: string
  summary: string
  topic: string
  topicKeywords: string[]
  imageUrl: string
  publishedAt: string
  updatedAt: string
  sourceCount?: number
  articleCount?: number
  topSources?: string[]
  articles?: Article[]
  spectrum: {
    min?: number
    max?: number
    average?: number
    knownCount: number
    unknownCount: number
    buckets: Record<SpectrumBucket, number>
  }
  scores: {
    coverageDiversity: number
    spectrumBalance: number
    headlineDivergence: number
    confidence: number
  }
  flags: string[]
}

export type ClusterDetail = Omit<Cluster, 'detailPath'> & {
  articles: Article[]
}

export type NewsPayload = {
  generatedAt: string
  version: string
  source: string
  stats: {
    clusterCount: number
    articleCount: number
    knownSources: number
    unknownSources: number
    imageFetchAttempts?: number
    articleImagesFromPreview?: number
    clusterImagesFromPreview?: number
    clusterImagesFromFallback?: number
  }
  clusters: Cluster[]
  sources: IndexedSourceMeta[]
}
