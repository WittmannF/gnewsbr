/** Remove LLM-leaked article IDs. Visible source citations remain linked separately. */
const citationGroup = /\s*\(\s*article_[a-f0-9]{8,}(?:\s*[,;]\s*article_[a-f0-9]{8,})*\s*\)/gi
const articleId = /\barticle_[a-f0-9]{8,}\b/gi

export function cleanReaderText(value: string): string {
  return value
    .replace(citationGroup, '')
    .replace(articleId, '')
    .replace(/\(\s*[,;]?\s*\)/g, '')
    .replace(/\s+([,;:.!?])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}
