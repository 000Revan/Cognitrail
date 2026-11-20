import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true })

// 助手回答只展示文本和链接，不自动加载模型提供的图片。
markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index]!.content)
markdown.validateLink = url => /^(https?:\/\/|\/(?!\/))/i.test(url) && !/[\s\\]|%5c/i.test(url)
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  const token = tokens[index]!
  if (/^https?:\/\//i.test(String(token.attrGet('href') || ''))) {
    token.attrSet('target', '_blank')
    token.attrSet('rel', 'noopener noreferrer')
  }
  return renderer.renderToken(tokens, index, options)
}

/** 将累积收到的助手 Markdown 转成 HTML；原始 HTML 始终作为文本处理。 */
export function renderAssistantMarkdown(content: string): string {
  return markdown.render(content)
}
