/** 受限Markdown只生成文本令牌，不生成或执行HTML。 */
export interface DiscussionToken { kind: 'text' | 'code' | 'strong' | 'link'; text: string; href?: string }
export function safeDiscussionUrl(value: string): string | null {
  if (!/^https?:\/\//i.test(value) || /\s/.test(value) || [...value].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127)) return null
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null
    return url.href
  } catch { return null }
}
export function discussionTokens(text: string): DiscussionToken[] {
  const pattern = /\[[^\]\n]{1,300}\]\([^\s)]{1,2048}\)|`[^`\n]{1,500}`|\*\*[^*\n]{1,500}\*\*/g
  const tokens: DiscussionToken[] = []
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index!, value = match[0]
    if (index > cursor) tokens.push({ kind: 'text', text: text.slice(cursor, index) })
    if (value.startsWith('`')) tokens.push({ kind: 'code', text: value.slice(1, -1) })
    else if (value.startsWith('**')) tokens.push({ kind: 'strong', text: value.slice(2, -2) })
    else {
      const middle = value.indexOf(']('), href = safeDiscussionUrl(value.slice(middle + 2, -1))
      tokens.push(href ? { kind: 'link', text: value.slice(1, middle), href } : { kind: 'text', text: value })
    }
    cursor = index + value.length
  }
  if (cursor < text.length) tokens.push({ kind: 'text', text: text.slice(cursor) })
  return tokens
}
