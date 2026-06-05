from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ArticleType(str, Enum):
    news = "news"
    analysis = "analysis"
    opinion = "opinion"
    interview = "interview"
    press_release = "press_release"
    other = "other"


class Tone(str, Enum):
    neutral = "neutral"
    critical = "critical"
    supportive = "supportive"
    alarmist = "alarmist"
    unclear = "unclear"


class HeadlineDivergenceLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ClaimStatus(str, Enum):
    reported = "reported"
    disputed = "disputed"
    unclear = "unclear"


# --- Raw content.json schema ---

class ArticleMetadata(BaseModel):
    bucket: str | None = None
    description: str | None = None
    id: str
    publishedAt: str | None = None
    source: str
    sourceCanonical: str | None = None
    sourceDomain: str | None = None
    title: str
    url: str


class ExtractedContent(BaseModel):
    text: str
    wordCount: int


class ExtractionMetadata(BaseModel):
    contentType: str | None = None
    fetchedAt: str
    method: str | None = None
    resolvedUrl: str | None = None
    status: str
    title: str | None = None
    wordCount: int | None = None


class RawArticleContent(BaseModel):
    archiveId: str
    article: ArticleMetadata
    articleRank: int | None = None
    clusterId: str
    content: ExtractedContent
    extraction: ExtractionMetadata


# --- Normalized article schema ---

class ArticleQuality(BaseModel):
    status: str  # "ok" | "low_quality_extraction" | "skipped"
    encodingRepairApplied: bool = False
    removedBoilerplateRatio: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class NormalizedArticle(BaseModel):
    archiveId: str
    articleId: str
    clusterId: str
    articleRank: int | None = None
    source: str
    sourceCanonical: str | None = None
    sourceDomain: str | None = None
    bucket: str | None = None
    title: str
    description: str | None = None
    url: str
    resolvedUrl: str | None = None
    publishedAt: str | None = None
    fetchedAt: str | None = None
    extractionMethod: str | None = None
    extractionStatus: str
    originalWordCount: int
    cleanWordCount: int
    cleanText: str
    contentHash: str
    quality: ArticleQuality


# --- Article summary schema ---

class KeyEntity(BaseModel):
    name: str
    type: str  # "person" | "organization" | "location" | "event" | "other"


class DateOrNumber(BaseModel):
    value: str
    context: str


class ArticleSummary(BaseModel):
    archiveId: str
    articleId: str
    clusterId: str
    source: str
    sourceDomain: str | None = None
    bucket: str | None = None
    title: str
    url: str
    publishedAt: str | None = None
    model: str
    promptVersion: str
    contentHash: str
    generatedAt: str
    summary: str
    whatHappened: str
    mainClaims: list[str] = Field(default_factory=list)
    keyEntities: list[KeyEntity] = Field(default_factory=list)
    datesAndNumbers: list[DateOrNumber] = Field(default_factory=list)
    articleType: ArticleType = ArticleType.news
    tone: Tone = Tone.neutral
    notableFraming: str = ""
    limitations: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.medium


# --- Cluster summary schema ---

class ReportedClaim(BaseModel):
    claim: str
    sources: list[str]
    status: ClaimStatus = ClaimStatus.reported


class CoverageDifference(BaseModel):
    bucket: str
    summary: str
    sources: list[str]


class HeadlineDivergence(BaseModel):
    level: HeadlineDivergenceLevel
    explanation: str


class ClusterSummary(BaseModel):
    clusterId: str
    model: str
    promptVersion: str
    generatedAt: str
    neutralHeadline: str
    neutralSummary: str
    whatHappened: str
    whyItMatters: str
    knownFacts: list[str] = Field(default_factory=list)
    reportedClaims: list[ReportedClaim] = Field(default_factory=list)
    coverageDifferences: list[CoverageDifference] = Field(default_factory=list)
    headlineDivergence: HeadlineDivergence
    openQuestions: list[str] = Field(default_factory=list)
    newsletterBlurb: str
    confidence: Confidence = Confidence.medium


# --- Newsletter schema ---

class NewsletterItem(BaseModel):
    clusterId: str
    title: str
    summary: str
    whyItMatters: str
    coverageNote: str
    confidence: Confidence


class NewsletterSection(BaseModel):
    name: str
    items: list[NewsletterItem]


class Newsletter(BaseModel):
    date: str
    generatedAt: str
    title: str
    intro: str
    sections: list[NewsletterSection]
