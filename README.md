# 知途工坊 Cognitrail

知途工坊是面向自学者的学习路线社区平台，以「路线 → 阶段 → 节点」组织学习目标、建议顺序与外部参考资源，提供路线创作、版本发布、社区发现与交流，并集成 AI 工坊助手进行流式问答和站内路线检索。

使用者可以发现适合自己的路线，自由选择节点学习并记录位置与进度；创作者可以持续维护路线，通过独立工作稿与发布快照管理更新。

· [后端镜像](https://hub.docker.com/r/moonmirror/cognitrail-backend) · [前端镜像](https://hub.docker.com/r/moonmirror/cognitrail-frontend)

## 功能介绍

| 模块       | 功能                                                                                    |
| ---------- | --------------------------------------------------------------------------------------- |
| 账号与资料 | 注册登录、刷新恢复登录状态、个人资料、头像上传、密码修改和隐私设置。                    |
| 路线创作   | 可视化编辑阶段与节点、配置节点说明和外部资源、保存工作稿、发布及归档恢复。              |
| 版本管理   | 工作稿与发布快照隔离；新版差异预览、主动升级、进度迁移与历史保留。                      |
| 社区发现   | 关键词搜索、难度筛选、排序、分页浏览、路线详情与收藏。                                  |
| 路线学习   | 自由选择阶段与节点、恢复阅读位置、手动完成与撤销、外链访问标记、每日打卡及日历。        |
| 交流与通知 | 路线话题、评论回复、话题处理、路线更新与话题订阅、站内通知。                            |
| 个人主页   | 路线作品、动态、关注与粉丝，以及按隐私设置展示的收藏和学习列表。                        |
| 工坊助手   | SSE 流式对话、意图识别、只读站内路线检索、Markdown 与路线链接展示、历史会话与重启续聊。 |
| 管理后台   | 账号管理、官方路线维护、内容举报与治理、操作审计及系统信息。                            |

路线发布后，作者继续编辑工作稿，线上发布版本保持稳定；学习者可以查看新版差异后自行选择升级。收藏、开始学习、关注及订阅分别操作。节点完成标记、外链访问提示和每日打卡分别记录。

## 技术栈

| 部分     | 技术                                                              |
| -------- | ----------------------------------------------------------------- |
| 前端     | Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router、Axios   |
| 后端     | Python 3.12、FastAPI、Pydantic 2、Uvicorn                         |
| 数据库   | MySQL 8.0、SQLAlchemy 2 异步 ORM、asyncmy、Alembic                |
| AI 助手  | LangChain、LangGraph、ChatOpenAI、ReAct、SSE、SQLite checkpointer |
| 身份认证 | JWT、Argon2、持久登录会话                                         |
| 日志     | structlog、request_id 请求关联                                    |
| 部署     | Docker、Docker Compose、Nginx                                     |
| 依赖管理 | uv、pnpm                                                          |

后端采用 Router → Service → CRUD 分层，数据库结构通过 Alembic 管理。站内通知使用数据库 outbox 与应用内后台任务投递。助手历史消息存储于 MySQL，运行上下文通过 SQLite 检查点持久化。

## Docker 快速启动

### 1. 获取项目

安装 Git、Docker 和 Docker Compose；Windows 使用 Docker Desktop 的 Linux 容器引擎。下面的命令以 PowerShell 为例。

```powershell
git clone https://github.com/000Revan/Cognitrail.git
cd Cognitrail
```

Compose 使用以下公开镜像：

| 服务   | 镜像                                 |
| ------ | ------------------------------------ |
| 前端   | `moonmirror/cognitrail-frontend:1.0` |
| 后端   | `moonmirror/cognitrail-backend:1.0`  |
| 数据库 | `mysql:8.0`                          |

### 2. 配置环境变量

在项目根目录执行，仅在文件不存在时复制模板：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

编辑根目录 `.env`，设置新数据库的密码：

```dotenv
MYSQL_ROOT_PASSWORD='替换为你设置的root密码'
DB_PASSWORD='替换为你设置的应用数据库密码'
```

编辑 `backend/.env`：

| 配置项                      | 填写方式                                         |
| --------------------------- | ------------------------------------------------ |
| `JWT_SECRET`                | 自行生成至少 32 字节的随机签名密钥，并保持稳定。 |
| `DB_REQUIRED_VERSION`       | 与 MySQL 服务端版本一致，按下一步查询结果填写。  |
| `LLM_API_KEY`               | 使用工坊助手时填写模型服务密钥。                 |
| `LLM_MODEL`                 | 填写支持工具调用和结构化输出的模型名称。         |
| `LLM_BASE_URL`              | 按模型服务要求填写 OpenAI 兼容接口地址。         |
| `LLM_TIMEOUT_SECONDS`       | 单次模型网络操作超时，默认 60 秒。               |
| `LLM_TOTAL_TIMEOUT_SECONDS` | 整轮生成总超时，默认 180 秒。                    |

当前模型客户端使用 DeepSeek 的 `thinking` 参数区分回答与意图识别，模型服务需支持对应参数。配置文件示例见 [后端环境变量模板](backend/.env.example)。

拉取镜像后，可使用后端镜像生成随机 JWT 密钥，将输出复制到 `backend/.env` 的 `JWT_SECRET`：

```powershell
docker compose config --quiet
docker compose pull
docker run --rm --entrypoint python moonmirror/cognitrail-backend:1.0 -c "import secrets; print(secrets.token_urlsafe(48))"
```

根目录 `.env` 为 Compose 提供数据库密码；`backend/.env` 通过 `env_file` 注入后端。Compose 将后端数据库地址覆盖为 `mysql:3306`，账号覆盖为 `cognitrail`，数据库名为 `cognitrail_community`，密码使用根目录的 `DB_PASSWORD`。容器运行所需真实配置保留在宿主机，通过环境变量注入，不打入镜像。

### 3. 启动数据库

```powershell
docker compose up -d mysql
docker compose ps
```

等待 MySQL 显示 `healthy` 后，查询版本，按提示输入根目录 `.env` 中的 root 密码：

```powershell
docker compose exec mysql mysql -u root -p -e "SELECT VERSION();"
```

将结果填写到 `backend/.env`，例如本项目已运行的 MySQL 版本为：

```dotenv
DB_REQUIRED_VERSION=8.0.46
```

版本校验采用精确匹配；如返回值包含连字符发行后缀，填写连字符前的版本号。`mysql:8.0` 是浮动标签，可以在确认使用版本后将 Compose 固定为具体版本或镜像摘要。

MySQL 容器首次启动会创建 `cognitrail_community` 数据库及应用账号。初始化环境变量对空数据卷生效，已有数据库的密码通过 SQL 修改。

### 4. 初始化数据表并启动

```powershell
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend alembic current
```

确认迁移成功，当前版本为 `c006_agent_history` 后启动全部服务：

```powershell
docker compose up -d
docker compose ps
```

打开 [http://localhost:8080](http://localhost:8080)，注册普通用户即可开始使用。

需要管理员账号时执行，密码通过交互输入：

```powershell
docker compose exec backend python -m scripts.create_admin --username local_admin --nickname 管理员
```

管理员使用独立后台管理内容；普通社区操作使用普通用户账号。

### 5. 常用管理命令

```powershell
# 查看应用日志
docker compose logs --tail 100 backend frontend

# 实时查看后端日志
docker compose logs -f backend

# 应用外部配置变更
docker compose up -d

# 停止服务，保留命名数据卷
docker compose down
```

| 内容                   | 保存位置                                     |
| ---------------------- | -------------------------------------------- |
| 业务数据及助手历史消息 | `mysql_data` 命名卷，容器内 `/var/lib/mysql` |
| 头像与助手检查点       | `backend_data` 命名卷，容器内 `/app/.data`   |

数据卷名称默认带有 `cognitrail_` 前缀。备份和迁移时配套保存 MySQL 数据及 SQLite 检查点；首次创建的新数据卷从空数据库开始。`docker compose down -v` 会删除命名数据卷，日常停止服务使用不带 `-v` 的命令。

前端通过 Nginx 同源转发 `/api/` 和 `/health` 至后端，数据库通过容器网络访问。仅修改 Compose 或外部 `.env` 后执行 `docker compose up -d` 即可应用配置；`restart` 不会重新注入环境变量。

## 本地开发运行

### 环境要求

- Python 3.12、uv。
- Node.js >=22.12.0、pnpm 12.11.2。
- MySQL 8.0，`DB_REQUIRED_VERSION` 与实际服务端版本一致。

### 后端

从项目根目录进入后端并安装依赖：

```powershell
cd backend
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run python -m scripts.configure_auth
```

编辑 `backend/.env` 的 `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD` 和 `DB_REQUIRED_VERSION`，连接你的本地数据库；助手配置与 Docker 部署使用相同变量。

在 MySQL 中创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS cognitrail_community
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

数据库账号需具备建表和创建触发器的权限。MySQL 开启二进制日志并使用普通迁移账号时，由数据库管理员配置 `log_bin_trust_function_creators=1`；项目 Compose 已包含该启动参数。

在 `backend` 目录执行：

```powershell
uv run alembic upgrade head
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

### 前端

另开终端，在项目根目录执行：

```powershell
cd frontend
pnpm install --frozen-lockfile
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
pnpm dev
```

访问 [http://127.0.0.1:5173](http://127.0.0.1:5173)。开发服务器默认将 `/api` 和 `/health` 代理到 `http://127.0.0.1:8000`；后端地址改变时调整 `VITE_API_PROXY_TARGET`。

## 从源码构建镜像

在项目根目录执行，分别使用两端目录作为构建上下文：

```powershell
docker build -t moonmirror/cognitrail-backend:1.0 ./backend
docker build -t moonmirror/cognitrail-frontend:1.0 ./frontend
```

前后端 `.dockerignore` 筛选构建文件，排除真实环境变量文件、运行数据、测试及本机依赖缓存。前端采用多阶段构建，最终运行镜像包含 Nginx 配置与静态打包结果。后端使用锁文件安装生产依赖，并以单 worker 运行。

## 代码结构

| 路径                                       | 职责                                    |
| ------------------------------------------ | --------------------------------------- |
| `frontend/src/`                            | 页面、组件、路由、状态管理与接口请求    |
| `frontend/nginx.conf`                      | 静态服务、SPA 路由回退与反向代理        |
| `backend/app/main.py`                      | FastAPI 应用入口                        |
| `backend/app/routers/`                     | HTTP 与 SSE 接口                        |
| `backend/app/services/`                    | 业务流程、权限和事务编排                |
| `backend/app/database/`                    | ORM 模型、数据库连接与 CRUD             |
| `backend/app/schemas/`                     | 请求与响应结构                          |
| `backend/app/agent/`                       | 模型连接、提示词、Graph、工具及对话服务 |
| `backend/app/config/`、`backend/app/core/` | 环境配置、认证、日志与基础设施          |
| `backend/migrations/`                      | 数据库版本迁移                          |
| `backend/scripts/`                         | JWT 密钥配置和管理员创建                |
| `docker-compose.yaml`                      | 前端、后端、MySQL 服务编排及持久化配置  |

## 后续更新方向

- AI 辅助设计路线结构草稿，支持多轮修改与预览确认。
- 围绕路线节点搜索候选外部资源，展示来源和匹配说明，供创作者审核选用。
- 持续完善路线发现与创作交互体验。
