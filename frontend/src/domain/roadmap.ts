import type { GraphStage, RoadmapDocument, StageInput, NodeInput, PublicationIssue } from '../types/roadmap'

/** 检查当前未保存的工作稿；只做本地反馈，发布前仍由服务端复核。 */
export function publicationIssues(document: RoadmapDocument): PublicationIssue[] {
  const issues: PublicationIssue[] = []
  type Location = Pick<PublicationIssue, 'stageId' | 'nodeId' | 'resourceId'>
  const add = (message: string, field: string, location: Location = {}) => issues.push({ message, field, ...location })
  function text(value: string | null | undefined, max: number, field: string, label: string, location: Location = {}, required = true) {
    if (required && !value?.trim()) add('请填写' + label, field, location)
    else if (value && [...value].length > max) add(label + '不能超过' + max + '字', field, location)
  }
  function coordinates(value: { canvasX: number; canvasY: number }, location: Location) {
    for (const field of ['canvasX', 'canvasY'] as const) {
      if (!Number.isFinite(value[field]) || value[field] < 0 || value[field] > 10000) add('画布坐标需在0至10000之间', field, location)
    }
  }
  text(document.title, 120, 'title', '路线标题')
  text(document.description, 1000, 'description', '路线描述')
  text(document.effortNote, 200, 'effortNote', '参考投入时间', {}, false)
  if (!document.stages.length) add('请至少添加一个阶段', 'stages')
  if (!document.stages.some(s => s.nodes.some(n => n.countsTowardProgress !== false))) add('请至少添加一个计入主线进度的节点', 'stages')
  if (document.stages.length > 40) add('路线最多包含40个阶段', 'stages')
  if (document.stages.reduce((sum, s) => sum + s.nodes.length, 0) > 500) add('路线最多包含500个节点', 'stages')
  let resources = 0
  for (const stage of document.stages) {
    const location = { stageId: stage.id }
    text(stage.title, 120, 'title', '阶段标题', location)
    text(stage.description, 10000, 'description', '阶段描述', location, false)
    coordinates(stage, location)
    if (!stage.nodes.length) add('阶段至少包含一个节点', 'nodes', location)
    if (stage.nodes.length > 80) add('阶段最多包含80个节点', 'nodes', location)
    for (const node of stage.nodes) {
      const location = { stageId: stage.id, nodeId: node.id }
      text(node.title, 150, 'title', '节点标题', location)
      text(node.content, 10000, 'content', '节点内容描述', location)
      text(node.tips, 10000, 'tips', '小贴士', location, false)
      coordinates(node, location)
      if (node.isOptional && node.countsTowardProgress !== false) add('拓展节点不能计入主线进度', 'isOptional', location)
      if (node.estimatedMinutes !== null && (!Number.isInteger(node.estimatedMinutes) || node.estimatedMinutes < 1 || node.estimatedMinutes > 2147483647)) add('参考时间需为1至2147483647的整数', 'estimatedMinutes', location)
      if (!node.resources.length) add('每个节点至少添加一项学习资源', 'resources', location)
      if (node.resources.length > 30) add('节点最多包含30项资源', 'resources', location)
      resources += node.resources.length
      for (const resource of node.resources) {
        const location = { stageId: stage.id, nodeId: node.id, resourceId: resource.id }
        text(resource.title, 200, 'title', '资源名称', location)
        if (!resource.resourceUrl.trim()) add('请填写资源链接', 'resourceUrl', location)
        else {
          try {
            const url = new URL(resource.resourceUrl)
            if (!/^https?:\/\//i.test(resource.resourceUrl) || !url.hostname || url.username || url.password || resource.resourceUrl.length > 2048 || [...resource.resourceUrl].some(char => char.charCodeAt(0) < 33)) throw new Error('invalid URL')
          } catch { add('请输入无凭证、无空白的有效HTTP/HTTPS资源链接', 'resourceUrl', location) }
        }
        if (resource.resourceType === 'document') add('资源类型请选择文章、视频、课程、书籍或其他', 'resourceType', location)
      }
    }
  }
  if (resources > 1500) add('路线最多包含1500项资源', 'stages')
  const stageIds = new Set(document.stages.map(s => s.id)), edges = new Set<string>()
  if (document.connections.length > 200) add('路线最多包含200条阶段连线', 'connections')
  for (const edge of document.connections) {
    const key = edge.source + ':' + edge.target
    if (edge.source === edge.target || !stageIds.has(edge.source) || !stageIds.has(edge.target) || edges.has(key)) add('请删除自连、重复或目标不存在的阶段连线', 'connections', { stageId: edge.source })
    edges.add(key)
  }
  return issues
}

/** 临时ID不复用数据库数字；同一次保存由服务端返回完整ID映射。 */
export function temporaryId() { return 'tmp_' + crypto.randomUUID().replaceAll('-', '') }
export function newStage(x = 60, y = 60): StageInput {
  return { id: temporaryId(), title: '新阶段', description: null, canvasX: x, canvasY: y, nodes: [] }
}
export function newNode(index = 0): NodeInput {
  return { id: temporaryId(), title: '新节点', content: '', estimatedMinutes: null, tips: null,
    isOptional: false, countsTowardProgress: true, changePolicy: 'retain',
    canvasX: 24, canvasY: 72 + index * 72, resources: [] }
}
export function stageSize(stage: GraphStage) {
  return { width: Math.max(360, ...stage.nodes.map(n => n.canvasX + 300)),
    height: Math.max(160, ...stage.nodes.map(n => n.canvasY + 72)) }
}
export function cleanDocument(document: RoadmapDocument) {
  return JSON.stringify(document)
}
export function difficultyName(value: string) {
  return ({ beginner: '入门', intermediate: '进阶', advanced: '高级' })[value] || value
}
export function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(value))
}
