"""发布完整性与状态规则，不依赖数据库会话。"""

from app.core.exceptions import AppError
from app.schemas.roadmap import RoadmapSave


def is_public_route(route, release, author) -> bool:
    """分发、治理、冻结访问和作者状态全部正常才允许公开分发。"""
    return bool(
        release
        and author
        and route.current_release_id == release.id
        and release.roadmap_id == route.id
        and route.distribution_status == "published"
        and route.author_archived_at is None
        and route.moderation_status == "normal"
        and release.content_access == "normal"
        and (route.roadmap_type == "official" or author.status == "active")
    )


def require_editable(status: str, archived: bool) -> None:
    """未归档且未下架即可编辑下一版工作稿。"""
    if archived:
        raise AppError(409, "ROADMAP_ARCHIVED", "请先从已归档恢复到仓库")
    if status == "disabled":
        raise AppError(409, "ROADMAP_DISABLED", "路线已被管理员下架，无法编辑或发布")


def publication_issues(data: RoadmapSave) -> list[dict]:
    """检查发布内容而非限制草稿保存，定位到具体阶段/节点/资源。"""
    issues = []

    def add(message, field, **location):
        issues.append({"message": message, "field": field, **location})

    if not data.description or not data.description.strip():
        add("请填写路线描述", "description")
    if not any(n.counts_toward_progress for s in data.stages for n in s.nodes):
        add("请至少添加一个计入主线进度的节点", "stages")
    if not data.stages:
        add("请至少添加一个阶段", "stages")
    for stage in data.stages:
        if not stage.title.strip():
            add("请填写阶段标题", "title", stageId=stage.id)
        if not stage.nodes:
            add("阶段至少包含一个节点", "nodes", stageId=stage.id)
        for node in stage.nodes:
            location = {"stageId": stage.id, "nodeId": node.id}
            if not node.title.strip():
                add("请填写节点标题", "title", **location)
            if not node.content.strip():
                add("请填写节点内容描述", "content", **location)
            if not node.resources:
                add("每个节点至少添加一项学习资源", "resources", **location)
            for resource in node.resources:
                for field, value, label in (
                    ("title", resource.title, "资源名称"),
                    ("resourceUrl", resource.resource_url, "资源链接"),
                ):
                    if not value.strip():
                        add(f"请填写{label}", field, resourceId=resource.id, **location)
    return issues


def learning_upgrade_plan(source, target, completed_keys, last_node_key, confirmations):
    """只从当前源快照规划迁移；语义看修订号，文本或资源变化仅供展示。"""
    old = {node["stableKey"]: node for node in source}
    new = {node["stableKey"]: node for node in target}
    required = {
        key
        for key in old.keys() & new.keys()
        if key in completed_keys and old[key]["revisionNo"] != new[key]["revisionNo"]
    }
    automatic = {
        key for key in old.keys() & new.keys() if key in completed_keys and key not in required
    }
    completed = automatic | {key for key in required if confirmations.get(key) == "keep"}
    rows = []
    fields = {
        "title": "renamed",
        "content": "content",
        "tips": "tips",
        "estimatedMinutes": "time",
        "resources": "resources",
        "isOptional": "optional",
        "countsTowardProgress": "progress",
        "stageKey": "moved",
        "position": "order",
        "revisionNo": "semantic",
        "canvasX": "layout",
        "canvasY": "layout",
    }
    for key in [*new, *(key for key in old if key not in new)]:
        before, after = old.get(key), new.get(key)
        changes = (
            ["added"]
            if before is None
            else ["removed"]
            if after is None
            else sorted({label for field, label in fields.items() if before[field] != after[field]})
        )
        if not changes:
            continue
        rows.append(
            {
                "stableKey": key,
                "sourceTitle": before["title"] if before else None,
                "targetTitle": after["title"] if after else None,
                "sourceStage": before["stageTitle"] if before else None,
                "targetStage": after["stageTitle"] if after else None,
                "changes": changes,
                "isCompleted": key in completed_keys,
                "requiresConfirmation": key in required,
                "sourceExcerpt": (before["content"] or "")[:1000]
                if before and ("content" in changes or "semantic" in changes)
                else None,
                "targetExcerpt": (after["content"] or "")[:1000]
                if after and ("content" in changes or "semantic" in changes)
                else None,
                "targetCountsTowardProgress": bool(after and after["countsTowardProgress"]),
            }
        )
    main = {key for key, node in new.items() if node["countsTowardProgress"]}
    source_main = {key for key, node in old.items() if node["countsTowardProgress"]}
    position = (
        last_node_key
        if last_node_key in new
        else next(
            (key for key in new if key in main and key not in completed), next(iter(new), None)
        )
    )
    return {
        "requiredKeys": required,
        "completedKeys": completed,
        "lastNodeKey": position,
        "sourceCompleted": len(source_main & completed_keys),
        "sourceTotal": len(source_main),
        "targetTotal": len(main),
        "completedMin": len(automatic & main),
        "completedMax": len((automatic | required) & main),
        "completedCount": len(completed & main),
        "nodeChanges": rows,
    }
