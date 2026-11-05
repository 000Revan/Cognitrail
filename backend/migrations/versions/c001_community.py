"""公开社区全新数据库基线，依据公开社区方向V1.0的31表目标设计。

仅供人工创建的新空库使用，不升级旧0001—0004数据库，不自动建库或清库。
此文件冻结列、索引、联合外键与MySQL 8.0.14触发器，不依赖可变ORM模型。
跨表授权、快照只读、语义修订及状态转换仍由后续服务层实现。
"""

import re

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "c001_community"
down_revision = None
branch_labels = None
depends_on = None

TABLE_SPECS = {
    "users": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "用户标识"),
            ("username", "VARCHAR(30)", "NN；UQ", None, "规范化账号名，创建后不随昵称修改"),
            ("password_hash", "VARCHAR(255)", "NN", None, "不可逆密码散列"),
            ("nickname", "VARCHAR(50)", "NN", None, "公开昵称"),
            ("avatar_url", "VARCHAR(2048)", "NULL", None, "头像地址，默认头像由前端处理"),
            ("bio", "VARCHAR(500)", "NN；默认空串", "", "公开个人简介"),
            ("role", "VARCHAR(16)", "NN；默认user；TRIGGER", "user", "user或admin"),
            ("status", "VARCHAR(16)", "NN；默认active；TRIGGER", "active", "active或disabled"),
            ("last_login_at", "DATETIME(6)", "NULL", None, "最后登录时间"),
            ("deactivated_at", "DATETIME(6)", "NULL", None, "账号停用时间"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("username",)],
        "indexes": [("status", "id")],
        "foreign_keys": [],
    },
    "user_auth_sessions": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "登录会话ID"),
            ("user_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "登录用户"),
            (
                "session_key",
                "CHAR(36)",
                "NN；UQ；ASCII",
                None,
                "随机会话标识，可作为JWT中的会话引用",
            ),
            ("issued_at", "DATETIME(6)", "NN", None, "签发时间"),
            ("expires_at", "DATETIME(6)", "NN", None, "会话过期时间"),
            ("revoked_at", "DATETIME(6)", "NULL", None, "撤销时间，退出或改密时设置"),
            ("last_seen_at", "DATETIME(6)", "NULL", None, "最后活动时间，可节流更新"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("session_key",)],
        "indexes": [("user_id", "revoked_at", "expires_at"), ("expires_at",)],
        "foreign_keys": [(("user_id",), "users", ("id",))],
    },
    "user_privacy_settings": {
        "columns": [
            ("user_id", "BIGINT UNSIGNED", "PK；FK→users.id", None, "一用户一份设置"),
            (
                "publish_public",
                "TINYINT UNSIGNED",
                "NN；默认1；TRIGGER",
                "1",
                "发布活动是否公开，取0或1",
            ),
            ("checkin_public", "TINYINT UNSIGNED", "NN；默认0；TRIGGER", "0", "打卡活动是否公开"),
            (
                "favorite_public",
                "TINYINT UNSIGNED",
                "NN；默认0；TRIGGER",
                "0",
                "收藏活动及列表是否公开",
            ),
            (
                "learning_public",
                "TINYINT UNSIGNED",
                "NN；默认0；TRIGGER",
                "0",
                "加入学习活动及在学列表是否公开",
            ),
            (
                "settings_version",
                "INT UNSIGNED",
                "NN；默认1；TRIGGER",
                "1",
                "并发和缓存失效版本，正整数",
            ),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [],
        "indexes": [],
        "foreign_keys": [(("user_id",), "users", ("id",))],
    },
    "user_follows": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "关系标识"),
            ("follower_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "关注发起人"),
            ("followee_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "被关注人"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("follower_id", "followee_id")],
        "indexes": [("followee_id", "id")],
        "foreign_keys": [
            (("follower_id",), "users", ("id",)),
            (("followee_id",), "users", ("id",)),
        ],
    },
    "skill_roadmaps": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "路线标识"),
            ("creator_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "作者"),
            ("title", "VARCHAR(120)", "NN", None, "工作稿标题"),
            (
                "summary",
                "VARCHAR(1000)",
                "NN；默认空串",
                "",
                "路线简介，统一描述内容、适合人群、基础要求与预期目标",
            ),
            (
                "difficulty",
                "VARCHAR(16)",
                "NN；默认beginner；TRIGGER",
                "beginner",
                "beginner或intermediate或advanced",
            ),
            (
                "effort_note",
                "VARCHAR(200)",
                "NULL",
                None,
                "选填参考投入时间；空白保存NULL且不显示，填写时注明仅供参考",
            ),
            (
                "license_code",
                "VARCHAR(64)",
                "NN；默认UNSPECIFIED",
                "UNSPECIFIED",
                "路线内容许可标识",
            ),
            ("license_url", "VARCHAR(2048)", "NULL", None, "自定义许可地址"),
            (
                "current_release_id",
                "BIGINT UNSIGNED",
                "NULL；联合FK见第9章",
                None,
                "当前公开版本指针",
            ),
            ("edit_version", "INT UNSIGNED", "NN；默认1；TRIGGER", "1", "工作稿乐观锁，正整数"),
            (
                "distribution_status",
                "VARCHAR(16)",
                "NN；默认draft；TRIGGER",
                "draft",
                "draft或published或archived",
            ),
            (
                "moderation_status",
                "VARCHAR(16)",
                "NN；默认normal；TRIGGER",
                "normal",
                "normal或disabled",
            ),
            ("author_archived_at", "DATETIME(6)", "NULL", None, "作者归档时间"),
            ("published_at", "DATETIME(6)", "NULL", None, "最近发布时刻"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("id", "current_release_id")],
        "indexes": [
            ("creator_id", "id"),
            ("distribution_status", "moderation_status", "published_at", "id"),
        ],
        "foreign_keys": [
            (("creator_id",), "users", ("id",)),
            (("current_release_id", "id"), "roadmap_releases", ("id", "roadmap_id")),
        ],
    },
    "roadmap_stages": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "工作稿阶段标识"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "所属路线"),
            ("stable_key", "CHAR(36)", "NN；ASCII区分大小写", None, "稳定UUID"),
            ("title", "VARCHAR(120)", "NN", None, "阶段名称"),
            ("description", "TEXT", "NULL", None, "阶段说明"),
            ("position", "INT UNSIGNED", "NN；TRIGGER", None, "同路线目录顺序，正整数"),
            ("canvas_x", "DECIMAL(12,2)", "NN；默认0", "0", "画布横坐标，可为负"),
            ("canvas_y", "DECIMAL(12,2)", "NN；默认0", "0", "画布纵坐标，可为负"),
            ("is_deleted", "TINYINT UNSIGNED", "NN；默认0；TRIGGER", "0", "软删除标记"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("roadmap_id", "stable_key"), ("id", "roadmap_id")],
        "indexes": [("roadmap_id", "is_deleted", "position")],
        "foreign_keys": [(("roadmap_id",), "skill_roadmaps", ("id",))],
    },
    "learning_nodes": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "工作稿节点标识"),
            (
                "roadmap_id",
                "BIGINT UNSIGNED",
                "NN；FK→skill_roadmaps.id",
                None,
                "所属路线，辅助一致性约束",
            ),
            ("stage_id", "BIGINT UNSIGNED", "NN；联合FK→roadmap_stages", None, "所属同路线阶段"),
            ("stable_key", "CHAR(36)", "NN；ASCII区分大小写", None, "任务稳定UUID"),
            ("title", "VARCHAR(150)", "NN", None, "节点标题"),
            ("content", "MEDIUMTEXT", "NULL", None, "学习目标与说明"),
            ("tips", "TEXT", "NULL", None, "可选提示"),
            ("position", "INT UNSIGNED", "NN；TRIGGER", None, "阶段内顺序，正整数"),
            ("is_optional", "TINYINT UNSIGNED", "NN；默认0；TRIGGER", "0", "是否拓展节点"),
            (
                "counts_toward_progress",
                "TINYINT UNSIGNED",
                "NN；默认1；TRIGGER",
                "1",
                "是否计入主线进度",
            ),
            ("revision_no", "INT UNSIGNED", "NN；默认1；TRIGGER", "1", "学习语义修订号，正整数"),
            (
                "change_policy",
                "VARCHAR(16)",
                "NN；默认retain；TRIGGER",
                "retain",
                "retain或reconfirm",
            ),
            ("canvas_x", "DECIMAL(12,2)", "NN；默认0", "0", "画布横坐标"),
            ("canvas_y", "DECIMAL(12,2)", "NN；默认0", "0", "画布纵坐标"),
            (
                "estimated_minutes",
                "INT UNSIGNED",
                "NULL；TRIGGER",
                None,
                "选填参考分钟；空值不显示，非空须正数并注明仅供参考",
            ),
            ("is_deleted", "TINYINT UNSIGNED", "NN；默认0；TRIGGER", "0", "软删除标记"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("roadmap_id", "stable_key"), ("id", "roadmap_id")],
        "indexes": [("stage_id", "is_deleted", "position")],
        "foreign_keys": [
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("stage_id", "roadmap_id"), "roadmap_stages", ("id", "roadmap_id")),
        ],
    },
    "node_resources": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "资源标识"),
            ("node_id", "BIGINT UNSIGNED", "NN；FK→learning_nodes.id", None, "所属节点"),
            ("title", "VARCHAR(200)", "NN", None, "资源名称"),
            ("url", "VARCHAR(2048)", "NN；SERVICE校验协议", None, "外链地址"),
            (
                "resource_type",
                "VARCHAR(16)",
                "NN；TRIGGER",
                None,
                "article或video或course或book或other",
            ),
            ("language_code", "VARCHAR(16)", "NULL", None, "语言标识，如zh-CN"),
            (
                "access_type",
                "VARCHAR(16)",
                "NN；默认unknown；TRIGGER",
                "unknown",
                "free或paid或freemium或unknown",
            ),
            ("position", "INT UNSIGNED", "NN；TRIGGER", None, "节点内资源顺序，正整数"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("node_id", "position")],
        "indexes": [],
        "foreign_keys": [(("node_id",), "learning_nodes", ("id",))],
    },
    "roadmap_stage_edges": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "边标识"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "所属路线"),
            ("source_stage_id", "BIGINT UNSIGNED", "NN；同路线联合FK", None, "起点阶段"),
            ("target_stage_id", "BIGINT UNSIGNED", "NN；同路线联合FK", None, "终点阶段"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("roadmap_id", "source_stage_id", "target_stage_id")],
        "indexes": [("roadmap_id", "target_stage_id")],
        "foreign_keys": [
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("source_stage_id", "roadmap_id"), "roadmap_stages", ("id", "roadmap_id")),
            (("target_stage_id", "roadmap_id"), "roadmap_stages", ("id", "roadmap_id")),
        ],
    },
    "roadmap_releases": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "发布版本ID"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "所属路线"),
            ("version_no", "INT UNSIGNED", "NN；TRIGGER", None, "路线内版本序号，正整数"),
            ("source_edit_version", "INT UNSIGNED", "NN；TRIGGER", None, "产生版本的工作稿修订号"),
            ("title", "VARCHAR(120)", "NN", None, "标题快照"),
            (
                "summary",
                "VARCHAR(1000)",
                "NN",
                None,
                "完整简介快照，保留作者描述的适合人群、基础要求与预期目标",
            ),
            ("difficulty", "VARCHAR(16)", "NN；TRIGGER", None, "难度快照，同工作稿枚举"),
            (
                "effort_note",
                "VARCHAR(200)",
                "NULL",
                None,
                "可选参考投入时间快照；NULL不显示，填写时注明仅供参考",
            ),
            ("license_code", "VARCHAR(64)", "NN", None, "许可快照"),
            ("license_url", "VARCHAR(2048)", "NULL", None, "许可地址快照"),
            ("update_summary", "VARCHAR(2000)", "NN", None, "本次更新说明，首次发布说明亦填写"),
            (
                "content_hash",
                "CHAR(64)",
                "NN；ASCII",
                None,
                "规范化快照SHA256，含结构资源，不含发布时间",
            ),
            ("published_by", "BIGINT UNSIGNED", "NN；FK→users.id", None, "实际发布操作者"),
            ("published_at", "DATETIME(6)", "NN", None, "发布时刻"),
            (
                "content_access",
                "VARCHAR(16)",
                "NN；默认normal；TRIGGER",
                "normal",
                "normal或restricted，治理字段",
            ),
        ],
        "uniques": [
            ("roadmap_id", "version_no"),
            ("roadmap_id", "source_edit_version"),
            ("id", "roadmap_id"),
        ],
        "indexes": [("roadmap_id", "published_at", "id")],
        "foreign_keys": [
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("published_by",), "users", ("id",)),
        ],
    },
    "release_stages": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "冻结阶段ID"),
            ("release_id", "BIGINT UNSIGNED", "NN；FK→roadmap_releases.id", None, "所属版本"),
            ("stable_key", "CHAR(36)", "NN；ASCII", None, "工作稿稳定身份副本"),
            ("title", "VARCHAR(120)", "NN", None, "标题快照"),
            ("description", "TEXT", "NULL", None, "说明快照"),
            ("position", "INT UNSIGNED", "NN；TRIGGER", None, "版本内阶段顺序，正整数"),
            ("canvas_x", "DECIMAL(12,2)", "NN", None, "横坐标快照"),
            ("canvas_y", "DECIMAL(12,2)", "NN", None, "纵坐标快照"),
        ],
        "uniques": [("id", "release_id"), ("release_id", "stable_key"), ("release_id", "position")],
        "indexes": [],
        "foreign_keys": [(("release_id",), "roadmap_releases", ("id",))],
    },
    "release_nodes": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "冻结节点ID"),
            ("release_id", "BIGINT UNSIGNED", "NN；FK→roadmap_releases.id", None, "所属版本"),
            ("stage_id", "BIGINT UNSIGNED", "NN；同版本联合FK", None, "所属冻结阶段"),
            ("stable_key", "CHAR(36)", "NN；ASCII", None, "跨版本任务身份"),
            ("title", "VARCHAR(150)", "NN", None, "标题快照"),
            ("content", "MEDIUMTEXT", "NULL", None, "正文快照"),
            ("tips", "TEXT", "NULL", None, "提示快照"),
            ("position", "INT UNSIGNED", "NN；TRIGGER", None, "阶段内顺序，正整数"),
            ("is_optional", "TINYINT UNSIGNED", "NN；TRIGGER", None, "拓展标记，0或1"),
            (
                "counts_toward_progress",
                "TINYINT UNSIGNED",
                "NN；TRIGGER",
                None,
                "是否计入分母，0或1",
            ),
            ("revision_no", "INT UNSIGNED", "NN；TRIGGER", None, "语义修订号，正整数"),
            ("change_policy", "VARCHAR(16)", "NN；TRIGGER", None, "retain或reconfirm"),
            ("canvas_x", "DECIMAL(12,2)", "NN", None, "横坐标快照"),
            ("canvas_y", "DECIMAL(12,2)", "NN", None, "纵坐标快照"),
            (
                "estimated_minutes",
                "INT UNSIGNED",
                "NULL；TRIGGER",
                None,
                "可选参考分钟快照；NULL不显示，非空须正数并注明仅供参考",
            ),
        ],
        "uniques": [("id", "release_id"), ("release_id", "stable_key"), ("stage_id", "position")],
        "indexes": [("release_id", "counts_toward_progress", "id")],
        "foreign_keys": [
            (("release_id",), "roadmap_releases", ("id",)),
            (("stage_id", "release_id"), "release_stages", ("id", "release_id")),
        ],
    },
    "release_resources": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "冻结资源ID"),
            ("release_id", "BIGINT UNSIGNED", "NN；FK→roadmap_releases.id", None, "所属发布版本"),
            ("node_id", "BIGINT UNSIGNED", "NN；同版本联合FK", None, "所属冻结节点"),
            ("title", "VARCHAR(200)", "NN", None, "资源名称"),
            ("url", "VARCHAR(2048)", "NN", None, "发布时外链地址"),
            (
                "resource_type",
                "VARCHAR(16)",
                "NN；TRIGGER",
                None,
                "article或video或course或book或other",
            ),
            ("language_code", "VARCHAR(16)", "NULL", None, "语言快照"),
            ("access_type", "VARCHAR(16)", "NN；TRIGGER", None, "free或paid或freemium或unknown"),
            ("position", "INT UNSIGNED", "NN；TRIGGER", None, "节点内顺序，正整数"),
        ],
        "uniques": [("node_id", "position")],
        "indexes": [("release_id", "id")],
        "foreign_keys": [
            (("release_id",), "roadmap_releases", ("id",)),
            (("node_id", "release_id"), "release_nodes", ("id", "release_id")),
        ],
    },
    "release_stage_edges": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "冻结边ID"),
            ("release_id", "BIGINT UNSIGNED", "NN；FK→roadmap_releases.id", None, "所属版本"),
            ("source_stage_id", "BIGINT UNSIGNED", "NN；同版本联合FK", None, "起点冻结阶段"),
            ("target_stage_id", "BIGINT UNSIGNED", "NN；同版本联合FK", None, "终点冻结阶段"),
        ],
        "uniques": [("release_id", "source_stage_id", "target_stage_id")],
        "indexes": [("release_id", "target_stage_id")],
        "foreign_keys": [
            (("release_id",), "roadmap_releases", ("id",)),
            (("source_stage_id", "release_id"), "release_stages", ("id", "release_id")),
            (("target_stage_id", "release_id"), "release_stages", ("id", "release_id")),
        ],
    },
    "roadmap_favorites": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "收藏标识"),
            ("user_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "收藏人"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "被收藏路线"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("user_id", "roadmap_id")],
        "indexes": [("roadmap_id", "id"), ("user_id", "created_at", "id")],
        "foreign_keys": [
            (("user_id",), "users", ("id",)),
            (("roadmap_id",), "skill_roadmaps", ("id",)),
        ],
    },
    "user_roadmaps": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "学习关系ID"),
            ("user_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "学习者"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "路线"),
            (
                "current_session_id",
                "BIGINT UNSIGNED",
                "NULL；联合FK见第9章",
                None,
                "初始化时暂空，提交前必须有效",
            ),
            ("status", "VARCHAR(16)", "NN；默认active；TRIGGER", "active", "active或abandoned"),
            ("started_at", "DATETIME(6)", "NN", None, "首次加入时间"),
            ("abandoned_at", "DATETIME(6)", "NULL", None, "退出时间"),
            (
                "dismissed_release_id",
                "BIGINT UNSIGNED",
                "NULL；同路线联合FK",
                None,
                "用户已忽略提醒的版本",
            ),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("user_id", "roadmap_id"), ("id", "roadmap_id")],
        "indexes": [("user_id", "status", "id"), ("roadmap_id", "id")],
        "foreign_keys": [
            (("user_id",), "users", ("id",)),
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (
                ("current_session_id", "id", "roadmap_id"),
                "learning_sessions",
                ("id", "user_roadmap_id", "roadmap_id"),
            ),
            (("dismissed_release_id", "roadmap_id"), "roadmap_releases", ("id", "roadmap_id")),
        ],
    },
    "learning_sessions": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "学习会话ID"),
            ("user_roadmap_id", "BIGINT UNSIGNED", "NN；同路线联合FK", None, "所属学习关系"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "所属路线"),
            ("release_id", "BIGINT UNSIGNED", "NN；同路线联合FK", None, "固定发布版本"),
            (
                "source_session_id",
                "BIGINT UNSIGNED",
                "NULL；FK→learning_sessions.id",
                None,
                "升级来源；首次加入为空",
            ),
            ("last_node_id", "BIGINT UNSIGNED", "NULL；同版本联合FK", None, "最后浏览冻结节点"),
            ("last_opened_at", "DATETIME(6)", "NULL", None, "最后浏览时间"),
            (
                "progress_version",
                "INT UNSIGNED",
                "NN；默认1；TRIGGER",
                "1",
                "完成状态或位置变更后递增，防止预览过期",
            ),
            ("started_at", "DATETIME(6)", "NN", None, "该版本开始学习时间"),
            (
                "first_completed_at",
                "DATETIME(6)",
                "NULL",
                None,
                "该版本首次全部主线完成时间，不因撤销抹去",
            ),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [
            ("user_roadmap_id", "release_id"),
            ("id", "release_id"),
            ("id", "user_roadmap_id"),
            ("id", "user_roadmap_id", "roadmap_id"),
        ],
        "indexes": [("user_roadmap_id", "started_at", "id")],
        "foreign_keys": [
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("source_session_id",), "learning_sessions", ("id",)),
            (("user_roadmap_id", "roadmap_id"), "user_roadmaps", ("id", "roadmap_id")),
            (("release_id", "roadmap_id"), "roadmap_releases", ("id", "roadmap_id")),
            (("last_node_id", "release_id"), "release_nodes", ("id", "release_id")),
        ],
    },
    "user_node_progress": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "进度行ID"),
            ("session_id", "BIGINT UNSIGNED", "NN；同版本联合FK", None, "所属会话"),
            ("release_id", "BIGINT UNSIGNED", "NN；FK→roadmap_releases.id", None, "版本约束冗余键"),
            ("release_node_id", "BIGINT UNSIGNED", "NN；同版本联合FK", None, "冻结节点"),
            (
                "is_completed",
                "TINYINT UNSIGNED",
                "NN；默认0；TRIGGER",
                "0",
                "0或1，缺行也表示未完成",
            ),
            ("completed_at", "DATETIME(6)", "NULL", None, "当前完成时间，撤销时清空"),
            (
                "completion_source",
                "VARCHAR(16)",
                "NN；默认manual；TRIGGER",
                "manual",
                "manual或migrated或confirmed",
            ),
            (
                "source_progress_id",
                "BIGINT UNSIGNED",
                "NULL；FK→user_node_progress.id",
                None,
                "迁移来源记录",
            ),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("session_id", "release_node_id")],
        "indexes": [("session_id", "is_completed", "release_node_id")],
        "foreign_keys": [
            (("release_id",), "roadmap_releases", ("id",)),
            (("source_progress_id",), "user_node_progress", ("id",)),
            (("session_id", "release_id"), "learning_sessions", ("id", "release_id")),
            (("release_node_id", "release_id"), "release_nodes", ("id", "release_id")),
        ],
    },
    "learning_session_events": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "事件ID"),
            ("user_roadmap_id", "BIGINT UNSIGNED", "NN；FK→user_roadmaps.id", None, "所属学习关系"),
            ("actor_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "实际操作用户"),
            ("event_type", "VARCHAR(16)", "NN；TRIGGER", None, "join或upgrade或abandon或resume"),
            ("from_session_id", "BIGINT UNSIGNED", "NULL；同关系联合FK", None, "源会话"),
            ("to_session_id", "BIGINT UNSIGNED", "NULL；同关系联合FK", None, "目标会话"),
            ("request_key", "VARCHAR(64)", "NN；ASCII", None, "操作幂等键"),
            ("details", "JSON", "NULL；SERVICE校验", None, "版本差异摘要与重新确认选择，不存笔记"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "事件发生时间",
            ),
        ],
        "uniques": [("user_roadmap_id", "request_key")],
        "indexes": [("user_roadmap_id", "created_at", "id")],
        "foreign_keys": [
            (("user_roadmap_id",), "user_roadmaps", ("id",)),
            (("actor_id",), "users", ("id",)),
            (
                ("from_session_id", "user_roadmap_id"),
                "learning_sessions",
                ("id", "user_roadmap_id"),
            ),
            (("to_session_id", "user_roadmap_id"), "learning_sessions", ("id", "user_roadmap_id")),
        ],
    },
    "roadmap_checkins": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "打卡ID"),
            ("user_roadmap_id", "BIGINT UNSIGNED", "NN；FK→user_roadmaps.id", None, "用户路线关系"),
            ("session_id", "BIGINT UNSIGNED", "NN；同关系联合FK", None, "打卡时学习版本会话"),
            ("checkin_date", "DATE", "NN", None, "统一业务时区自然日"),
            (
                "timezone_name",
                "VARCHAR(64)",
                "NN；默认Asia/Shanghai",
                "Asia/Shanghai",
                "日期口径快照",
            ),
            ("is_valid", "TINYINT UNSIGNED", "NN；默认1；TRIGGER", "1", "治理撤销设0"),
            ("invalidated_at", "DATETIME(6)", "NULL", None, "撤销时间"),
            ("invalidated_by", "BIGINT UNSIGNED", "NULL；FK→users.id", None, "治理操作者"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "打卡实际发生时间 UTC",
            ),
        ],
        "uniques": [("user_roadmap_id", "checkin_date")],
        "indexes": [("checkin_date", "is_valid", "id")],
        "foreign_keys": [
            (("user_roadmap_id",), "user_roadmaps", ("id",)),
            (("invalidated_by",), "users", ("id",)),
            (("session_id", "user_roadmap_id"), "learning_sessions", ("id", "user_roadmap_id")),
        ],
    },
    "roadmap_issues": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "主题ID"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "所属路线"),
            ("author_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "提问者"),
            ("title", "VARCHAR(150)", "NN", None, "用户自由填写的话题标题"),
            (
                "body",
                "MEDIUMTEXT",
                "NN",
                None,
                "话题正文，受限Markdown；可自行描述位置或粘贴相关链接",
            ),
            ("status", "VARCHAR(16)", "NN；默认open；TRIGGER", "open", "open或resolved或closed"),
            (
                "visibility",
                "VARCHAR(16)",
                "NN；默认public；TRIGGER",
                "public",
                "public或hidden或deleted",
            ),
            ("state_reason", "VARCHAR(500)", "NULL", None, "最近状态处理原因"),
            ("state_changed_by", "BIGINT UNSIGNED", "NULL；FK→users.id", None, "最近状态操作者"),
            ("last_activity_at", "DATETIME(6)", "NN", None, "最近有效回复或状态变更时间"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("id", "roadmap_id")],
        "indexes": [
            ("roadmap_id", "visibility", "status", "last_activity_at", "id"),
            ("author_id", "created_at", "id"),
        ],
        "foreign_keys": [
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("author_id",), "users", ("id",)),
            (("state_changed_by",), "users", ("id",)),
        ],
    },
    "issue_comments": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "回复ID"),
            ("issue_id", "BIGINT UNSIGNED", "NN；FK→roadmap_issues.id", None, "所属主题"),
            ("author_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "回复人"),
            (
                "reply_to_comment_id",
                "BIGINT UNSIGNED",
                "NULL；同主题联合FK",
                None,
                "被回复评论，可空",
            ),
            ("body", "MEDIUMTEXT", "NN", None, "回复正文"),
            (
                "visibility",
                "VARCHAR(16)",
                "NN；默认public；TRIGGER",
                "public",
                "public或hidden或deleted",
            ),
            ("edited_at", "DATETIME(6)", "NULL", None, "最后编辑时间"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("id", "issue_id")],
        "indexes": [("issue_id", "created_at", "id"), ("author_id", "created_at", "id")],
        "foreign_keys": [
            (("issue_id",), "roadmap_issues", ("id",)),
            (("author_id",), "users", ("id",)),
            (("reply_to_comment_id", "issue_id"), "issue_comments", ("id", "issue_id")),
        ],
    },
    "issue_subscriptions": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "订阅ID"),
            ("issue_id", "BIGINT UNSIGNED", "NN；FK→roadmap_issues.id", None, "主题"),
            ("user_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "订阅人"),
            ("is_subscribed", "TINYINT UNSIGNED", "NN；默认1；TRIGGER", "1", "0或1，显式退订写0"),
            ("subscription_source", "VARCHAR(16)", "NN；TRIGGER", None, "author或creator或manual"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("issue_id", "user_id")],
        "indexes": [("user_id", "is_subscribed", "id")],
        "foreign_keys": [
            (("issue_id",), "roadmap_issues", ("id",)),
            (("user_id",), "users", ("id",)),
        ],
    },
    "issue_events": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "事件ID"),
            ("issue_id", "BIGINT UNSIGNED", "NN；FK→roadmap_issues.id", None, "主题"),
            ("actor_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "操作者"),
            (
                "event_type",
                "VARCHAR(24)",
                "NN；TRIGGER",
                None,
                "created或edited或resolved或closed或reopened或hidden或restored",
            ),
            (
                "from_status",
                "VARCHAR(16)",
                "NULL；TRIGGER",
                None,
                "原业务状态，open或resolved或closed",
            ),
            ("to_status", "VARCHAR(16)", "NULL；TRIGGER", None, "新业务状态，枚举同上"),
            ("reason", "VARCHAR(500)", "NULL", None, "处理理由，关闭必填"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "发生时间",
            ),
        ],
        "uniques": [],
        "indexes": [("issue_id", "created_at", "id")],
        "foreign_keys": [
            (("issue_id",), "roadmap_issues", ("id",)),
            (("actor_id",), "users", ("id",)),
        ],
    },
    "roadmap_subscriptions": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "订阅ID"),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "被订阅路线"),
            ("user_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "订阅人"),
            ("is_subscribed", "TINYINT UNSIGNED", "NN；默认1；TRIGGER", "1", "是否订阅新版本"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("roadmap_id", "user_id")],
        "indexes": [("user_id", "is_subscribed", "id")],
        "foreign_keys": [
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("user_id",), "users", ("id",)),
        ],
    },
    "activity_events": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "活动ID"),
            ("actor_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "行为人"),
            (
                "activity_type",
                "VARCHAR(16)",
                "NN；TRIGGER",
                None,
                "publish或checkin或favorite或learning",
            ),
            ("roadmap_id", "BIGINT UNSIGNED", "NN；FK→skill_roadmaps.id", None, "活动涉及路线"),
            ("release_id", "BIGINT UNSIGNED", "NULL；同路线联合FK", None, "发布更新版本"),
            ("checkin_id", "BIGINT UNSIGNED", "NULL；FK→roadmap_checkins.id", None, "打卡来源"),
            ("event_key", "VARCHAR(120)", "NN；UQ；ASCII", None, "事实事件幂等标识"),
            (
                "visibility",
                "VARCHAR(16)",
                "NN；默认public；TRIGGER",
                "public",
                "public或private，分类设置仍需共同判断",
            ),
            (
                "is_active",
                "TINYINT UNSIGNED",
                "NN；默认1；TRIGGER",
                "1",
                "取消收藏、退出学习等使活动失效",
            ),
            ("occurred_on", "DATE", "NN", None, "事件业务日期，用于打卡聚合"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "发生时间",
            ),
        ],
        "uniques": [("event_key",)],
        "indexes": [
            ("actor_id", "created_at", "id"),
            ("actor_id", "activity_type", "occurred_on", "id"),
        ],
        "foreign_keys": [
            (("actor_id",), "users", ("id",)),
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("checkin_id",), "roadmap_checkins", ("id",)),
            (("release_id", "roadmap_id"), "roadmap_releases", ("id", "roadmap_id")),
        ],
    },
    "notification_outbox": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "任务ID"),
            ("event_key", "VARCHAR(120)", "NN；UQ；ASCII", None, "领域事件唯一键"),
            (
                "event_type",
                "VARCHAR(32)",
                "NN；SERVICE校验",
                None,
                "issue_created、comment_created、issue_state_changed、release_published、moderation_notice",
            ),
            (
                "payload",
                "JSON",
                "NN；SERVICE校验",
                None,
                "仅存对象ID及事件必要参数，不复制私密正文",
            ),
            (
                "status",
                "VARCHAR(16)",
                "NN；默认pending；TRIGGER",
                "pending",
                "pending或processing或done或failed",
            ),
            ("attempts", "INT UNSIGNED", "NN；默认0", "0", "已尝试次数"),
            ("available_at", "DATETIME(6)", "NN", None, "下次可执行时间"),
            ("lease_until", "DATETIME(6)", "NULL", None, "处理租约截止，崩溃后可重领"),
            ("lease_token", "CHAR(36)", "NULL；ASCII", None, "任务认领令牌，防止过期工作进程提交"),
            ("last_error", "VARCHAR(1000)", "NULL", None, "脱敏后的错误摘要"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [("event_key",)],
        "indexes": [("status", "available_at", "id"), ("status", "lease_until", "id")],
        "foreign_keys": [],
    },
    "notifications": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "通知ID"),
            ("recipient_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "接收者"),
            ("actor_id", "BIGINT UNSIGNED", "NULL；FK→users.id", None, "行为人，系统消息可空"),
            ("notification_type", "VARCHAR(32)", "NN；SERVICE校验", None, "与outbox事件类型一致"),
            ("event_key", "VARCHAR(120)", "NN；ASCII", None, "来源事件幂等键"),
            ("roadmap_id", "BIGINT UNSIGNED", "NULL；FK→skill_roadmaps.id", None, "路线目标"),
            ("issue_id", "BIGINT UNSIGNED", "NULL；FK→roadmap_issues.id", None, "主题目标"),
            ("comment_id", "BIGINT UNSIGNED", "NULL；同主题联合FK", None, "回复锚点"),
            ("release_id", "BIGINT UNSIGNED", "NULL；同路线联合FK", None, "版本目标"),
            ("system_message", "VARCHAR(500)", "NULL", None, "仅治理说明等系统文本，不存讨论正文"),
            ("read_at", "DATETIME(6)", "NULL", None, "NULL表示未读"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间",
            ),
        ],
        "uniques": [("recipient_id", "event_key")],
        "indexes": [("recipient_id", "read_at", "id"), ("recipient_id", "created_at", "id")],
        "foreign_keys": [
            (("recipient_id",), "users", ("id",)),
            (("actor_id",), "users", ("id",)),
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("issue_id",), "roadmap_issues", ("id",)),
            (("release_id", "roadmap_id"), "roadmap_releases", ("id", "roadmap_id")),
            (("comment_id", "issue_id"), "issue_comments", ("id", "issue_id")),
        ],
    },
    "content_reports": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "举报ID"),
            ("reporter_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "举报人，非公开资料"),
            ("roadmap_id", "BIGINT UNSIGNED", "NULL；FK→skill_roadmaps.id", None, "路线举报目标"),
            ("issue_id", "BIGINT UNSIGNED", "NULL；FK→roadmap_issues.id", None, "主题举报目标"),
            ("comment_id", "BIGINT UNSIGNED", "NULL；FK→issue_comments.id", None, "评论举报目标"),
            (
                "reason_code",
                "VARCHAR(32)",
                "NN；SERVICE校验",
                None,
                "垃圾广告、侵权、违规等受控原因码",
            ),
            ("description", "VARCHAR(2000)", "NN；默认空串", "", "补充描述"),
            (
                "status",
                "VARCHAR(16)",
                "NN；默认pending；TRIGGER",
                "pending",
                "pending或processing或resolved或rejected",
            ),
            ("handled_by", "BIGINT UNSIGNED", "NULL；FK→users.id", None, "处理管理员"),
            ("handled_at", "DATETIME(6)", "NULL", None, "结案时间"),
            ("result_note", "VARCHAR(1000)", "NULL", None, "处理结论，向举报人展示时脱敏"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "创建时间 UTC",
            ),
            (
                "updated_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "修改时间 UTC，由服务层更新",
            ),
        ],
        "uniques": [],
        "indexes": [("status", "created_at", "id"), ("reporter_id", "created_at", "id")],
        "foreign_keys": [
            (("reporter_id",), "users", ("id",)),
            (("roadmap_id",), "skill_roadmaps", ("id",)),
            (("issue_id",), "roadmap_issues", ("id",)),
            (("comment_id",), "issue_comments", ("id",)),
            (("handled_by",), "users", ("id",)),
        ],
    },
    "moderation_actions": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "治理记录ID"),
            ("actor_id", "BIGINT UNSIGNED", "NN；FK→users.id", None, "管理操作者"),
            ("report_id", "BIGINT UNSIGNED", "NULL；FK→content_reports.id", None, "来源举报"),
            (
                "target_type",
                "VARCHAR(24)",
                "NN；TRIGGER",
                None,
                "user或roadmap或release或issue或comment或checkin",
            ),
            ("target_id", "BIGINT UNSIGNED", "NN", None, "多态目标，SERVICE验证存在"),
            ("action", "VARCHAR(24)", "NN；TRIGGER", None, "disable或restore或hide或invalidate"),
            ("reason", "VARCHAR(1000)", "NN", None, "处理原因"),
            ("before_state", "JSON", "NULL", None, "必要的原控制状态，不复制正文"),
            ("after_state", "JSON", "NULL", None, "新的控制状态"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "处理时间",
            ),
        ],
        "uniques": [],
        "indexes": [
            ("target_type", "target_id", "created_at", "id"),
            ("actor_id", "created_at", "id"),
        ],
        "foreign_keys": [
            (("actor_id",), "users", ("id",)),
            (("report_id",), "content_reports", ("id",)),
        ],
    },
    "audit_logs": {
        "columns": [
            ("id", "BIGINT UNSIGNED", "PK；AI", None, "审计ID"),
            ("actor_id", "BIGINT UNSIGNED", "NULL；FK→users.id", None, "操作者，系统任务可空"),
            ("action_code", "VARCHAR(64)", "NN", None, "受控操作编码"),
            ("target_type", "VARCHAR(32)", "NN", None, "对象类型"),
            ("target_id", "BIGINT UNSIGNED", "NULL", None, "对象标识，多态引用"),
            ("request_id", "VARCHAR(64)", "NN；ASCII", None, "请求追踪ID"),
            ("result", "VARCHAR(16)", "NN；TRIGGER", None, "success或failure"),
            ("details", "JSON", "NULL", None, "必要上下文，不含密码令牌或私密正文"),
            (
                "created_at",
                "DATETIME(6)",
                "NN；默认CURRENT_TIMESTAMP(6)",
                "CURRENT_TIMESTAMP(6)",
                "事件时间",
            ),
        ],
        "uniques": [],
        "indexes": [
            ("request_id",),
            ("target_type", "target_id", "created_at", "id"),
            ("actor_id", "created_at", "id"),
        ],
        "foreign_keys": [(("actor_id",), "users", ("id",))],
    },
}

ENUM_COLUMNS = {
    "activity_events": ("activity_type", "visibility"),
    "audit_logs": ("result",),
    "content_reports": ("status",),
    "issue_comments": ("visibility",),
    "issue_events": ("event_type", "from_status", "to_status"),
    "issue_subscriptions": ("subscription_source",),
    "learning_nodes": ("change_policy",),
    "learning_session_events": ("event_type",),
    "moderation_actions": ("target_type", "action"),
    "node_resources": ("resource_type", "access_type"),
    "notification_outbox": ("status",),
    "release_nodes": ("change_policy",),
    "release_resources": ("resource_type", "access_type"),
    "roadmap_issues": ("status", "visibility"),
    "roadmap_releases": ("difficulty", "content_access"),
    "skill_roadmaps": ("difficulty", "distribution_status", "moderation_status"),
    "user_node_progress": ("completion_source",),
    "user_roadmaps": ("status",),
    "users": ("role", "status"),
}

TRIGGER_RULES = {
    "users": "(NEW.role IN ('user', 'admin')) AND (NEW.status IN ('active', 'disabled'))",
    "user_auth_sessions": "(NEW.expires_at > NEW.issued_at)",
    "user_privacy_settings": "(NEW.publish_public IN (0, 1)) AND "
    "(NEW.checkin_public IN (0, 1)) AND "
    "(NEW.favorite_public IN (0, 1)) AND (NEW.learning_public IN (0, 1)) AND "
    "(NEW.settings_version > 0)",
    "user_follows": "(NEW.follower_id <> NEW.followee_id)",
    "skill_roadmaps": "(NEW.difficulty IN ('beginner', 'intermediate', 'advanced')) AND "
    "(NEW.edit_version > 0) AND (NEW.distribution_status IN ('draft', 'published', "
    "'archived')) AND (NEW.moderation_status IN ('normal', 'disabled'))",
    "roadmap_stages": "(NEW.position > 0) AND (NEW.is_deleted IN (0, 1))",
    "learning_nodes": "(NEW.position > 0) AND (NEW.is_optional IN (0, 1)) AND "
    "(NEW.counts_toward_progress IN (0, 1)) AND (NEW.revision_no > 0) AND "
    "(NEW.change_policy IN ('retain', 'reconfirm')) AND (NEW.estimated_minutes IS "
    "NULL OR (NEW.estimated_minutes > 0)) AND (NEW.is_deleted IN (0, 1)) AND "
    "(NEW.is_optional = 0 OR NEW.counts_toward_progress = 0)",
    "node_resources": "(NEW.resource_type IN ('article', 'video', 'course', 'book', 'other')) AND "
    "(NEW.access_type IN ('free', 'paid', 'freemium', 'unknown')) AND (NEW.position "
    "> 0)",
    "roadmap_stage_edges": "(NEW.source_stage_id <> NEW.target_stage_id)",
    "roadmap_releases": "(NEW.version_no > 0) AND (NEW.source_edit_version > 0) AND "
    "(NEW.difficulty "
    "IN ('beginner', 'intermediate', 'advanced')) AND (NEW.content_access IN "
    "('normal', 'restricted'))",
    "release_stages": "(NEW.position > 0)",
    "release_nodes": "(NEW.position > 0) AND (NEW.is_optional IN (0, 1)) AND "
    "(NEW.counts_toward_progress IN (0, 1)) AND (NEW.revision_no > 0) AND "
    "(NEW.change_policy IN ('retain', 'reconfirm')) AND (NEW.estimated_minutes IS "
    "NULL OR (NEW.estimated_minutes > 0)) AND (NEW.is_optional = 0 OR "
    "NEW.counts_toward_progress = 0)",
    "release_resources": "(NEW.resource_type IN ('article', 'video', 'course', 'book', 'other')) "
    "AND (NEW.access_type IN ('free', 'paid', 'freemium', 'unknown')) AND "
    "(NEW.position > 0)",
    "release_stage_edges": "(NEW.source_stage_id <> NEW.target_stage_id)",
    "roadmap_favorites": "(NEW.user_id > 0) AND (NEW.roadmap_id > 0)",
    "user_roadmaps": "(NEW.status IN ('active', 'abandoned'))",
    "learning_sessions": "(NEW.progress_version > 0)",
    "user_node_progress": "(NEW.is_completed IN (0, 1)) AND (NEW.completion_source IN ('manual', "
    "'migrated', 'confirmed')) AND ((NEW.is_completed = 0 AND NEW.completed_at "
    "IS NULL) OR (NEW.is_completed = 1 AND NEW.completed_at IS NOT NULL)) AND "
    "(NEW.source_progress_id IS NULL OR NEW.source_progress_id <> NEW.id)",
    "learning_session_events": "(NEW.event_type IN ('join', 'upgrade', 'abandon', 'resume')) AND "
    "((NEW.event_type = 'join' AND NEW.from_session_id IS NULL AND "
    "NEW.to_session_id IS NOT NULL) OR (NEW.event_type = 'upgrade' AND "
    "NEW.from_session_id IS NOT NULL AND NEW.to_session_id IS NOT NULL AND "
    "NEW.from_session_id <> NEW.to_session_id) OR (NEW.event_type = "
    "'abandon' AND NEW.from_session_id IS NOT NULL AND NEW.to_session_id "
    "IS NULL) OR (NEW.event_type = 'resume' AND NEW.from_session_id IS "
    "NULL AND NEW.to_session_id IS NOT NULL))",
    "roadmap_checkins": "(NEW.is_valid IN (0, 1))",
    "roadmap_issues": "(NEW.status IN ('open', 'resolved', 'closed')) AND (NEW.visibility IN "
    "('public', 'hidden', 'deleted'))",
    "issue_comments": "(NEW.visibility IN ('public', 'hidden', 'deleted')) AND "
    "(NEW.reply_to_comment_id IS NULL OR NEW.reply_to_comment_id <> NEW.id)",
    "issue_subscriptions": "(NEW.is_subscribed IN (0, 1)) AND "
    "(NEW.subscription_source IN ('author', "
    "'creator', 'manual'))",
    "issue_events": "(NEW.event_type IN ('created', 'edited', 'resolved', 'closed', 'reopened', "
    "'hidden', 'restored')) AND (NEW.from_status IS NULL OR (NEW.from_status IN "
    "('open', 'resolved', 'closed'))) AND (NEW.to_status IS NULL OR (NEW.to_status IN "
    "('open', 'resolved', 'closed'))) AND (NEW.event_type <> 'closed' OR "
    "CHAR_LENGTH(TRIM(COALESCE(NEW.reason, ''))) > 0)",
    "roadmap_subscriptions": "(NEW.is_subscribed IN (0, 1))",
    "activity_events": "(NEW.activity_type IN ('publish', 'checkin', 'favorite', 'learning')) AND "
    "(NEW.visibility IN ('public', 'private')) AND (NEW.is_active IN (0, 1))",
    "notification_outbox": "(NEW.status IN ('pending', 'processing', 'done', 'failed'))",
    "notifications": "(NEW.comment_id IS NULL OR NEW.issue_id IS NOT NULL) AND (NEW.release_id IS "
    "NULL OR NEW.roadmap_id IS NOT NULL)",
    "content_reports": "(NEW.status IN ('pending', 'processing', 'resolved', 'rejected')) AND "
    "((NEW.roadmap_id IS NOT NULL) + (NEW.issue_id IS NOT NULL) + (NEW.comment_id "
    "IS NOT NULL) = 1)",
    "moderation_actions": "(NEW.target_type IN ('user', 'roadmap', 'release', 'issue', 'comment', "
    "'checkin')) AND (NEW.action IN ('disable', 'restore', 'hide', "
    "'invalidate'))",
    "audit_logs": "(NEW.result IN ('success', 'failure'))",
}


def _column_type(kind, ascii_value):
    """按冻结字典构建MySQL类型，业务ID一律无符号。"""
    if kind in {"BIGINT UNSIGNED", "INT UNSIGNED", "TINYINT UNSIGNED"}:
        type_name = "INTEGER" if kind.startswith("INT ") else kind.split()[0]
        return getattr(mysql, type_name)(unsigned=True)
    if kind == "DATETIME(6)":
        return mysql.DATETIME(fsp=6)
    if kind == "DECIMAL(12,2)":
        return mysql.DECIMAL(12, 2)
    match = re.fullmatch(r"(VAR)?CHAR\((\d+)\)", kind)
    if match:
        options = {"charset": "ascii", "collation": "ascii_bin"} if ascii_value else {}
        return getattr(mysql, "VARCHAR" if match[1] else "CHAR")(int(match[2]), **options)
    return getattr(mysql, kind)()


def _metadata():
    """先建全部表再补命名外键，显式处理路线与会话的循环指针。"""
    result = sa.MetaData()
    for name, spec in TABLE_SPECS.items():
        columns = []
        for col, kind, flags, default, comment in spec["columns"]:
            kwargs = {}
            if default is not None:
                if default == "CURRENT_TIMESTAMP(6)" or str(default).isdecimal():
                    kwargs["server_default"] = sa.text(str(default))
                else:
                    kwargs["server_default"] = sa.text("'" + default.replace("'", "''") + "'")
            primary = "PK" in flags
            columns.append(
                sa.Column(
                    col,
                    _column_type(kind, "ASCII" in flags or col in ENUM_COLUMNS.get(name, ())),
                    nullable=not (primary or "NN" in flags),
                    primary_key=primary,
                    autoincrement="AI" in flags,
                    comment=comment,
                    **kwargs,
                )
            )
        table = sa.Table(
            name,
            result,
            *columns,
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_0900_ai_ci",
        )
        for number, cols in enumerate(spec["uniques"], 1):
            table.append_constraint(sa.UniqueConstraint(*cols, name=f"uq_{name}_{number}"))
        for number, cols in enumerate(spec["indexes"], 1):
            sa.Index(f"idx_{name}_{number}", *(table.c[col] for col in cols))
    for name, spec in TABLE_SPECS.items():
        table = result.tables[name]
        for number, (local, parent, remote) in enumerate(spec["foreign_keys"], 1):
            table.append_constraint(
                sa.ForeignKeyConstraint(
                    local,
                    [f"{parent}.{col}" for col in remote],
                    name=f"fk_{name}_{number}",
                    ondelete="RESTRICT",
                    onupdate="RESTRICT",
                    use_alter=True,
                )
            )
            keys = [
                tuple(c.name for c in key.columns)
                for key in table.constraints
                if isinstance(key, sa.PrimaryKeyConstraint | sa.UniqueConstraint)
            ]
            keys += [tuple(c.name for c in index.columns) for index in table.indexes]
            if not any(key[: len(local)] == local for key in keys):
                sa.Index(f"idx_{name}_fk_{number}", *(table.c[col] for col in local))
    return result


metadata = _metadata()


def validate_database_state(tables, revisions):
    """只接受新空库或本基线完整数据库，拒绝旧历史、手工stamp与半成品。"""
    business = set(tables) - {"alembic_version"}
    if not revisions:
        if business:
            raise RuntimeError("新初始迁移只接受空库，不接管已有业务表")
    elif list(revisions) != [revision] or business != set(metadata.tables):
        raise RuntimeError("目标库不是完整的新社区基线，请使用新空库；未执行迁移")


def upgrade():
    """只创建新库表结构；在线空库预检由env.py执行，离线仅输出DDL。"""
    if not context.is_offline_mode():
        tables = sa.inspect(op.get_bind()).get_table_names()
        if set(tables) - {"alembic_version"}:
            raise RuntimeError("初始迁移不能写入非空业务库")
    metadata.create_all(bind=op.get_bind(), checkfirst=False)
    for name, rule in TRIGGER_RULES.items():
        for prefix, event in (("bi", "INSERT"), ("bu", "UPDATE")):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {prefix}_{name}_validate BEFORE {event} ON {name} "
                    f"FOR EACH ROW BEGIN IF COALESCE(({rule}), 0) = 0 THEN "
                    f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invalid_{name}'; END IF; END"
                )
            )


def downgrade():
    """保护新产生的社区数据，回退通过经核对的备份执行。"""
    raise RuntimeError("新初始基线不提供自动清库，请使用备份或另建空库")
