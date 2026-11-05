# 知途工坊 Cognitrail

面向自学者的学习路线社区平台。用户可以发现并收藏公开路线，围绕阶段、节点和推荐资源开展学习，也可以创建自己的路线并发布到社区。

## 功能概览

- **账号与资料**：注册、登录、修改密码、头像上传、个人资料和隐私设置。
- **路线创作**：编辑工作稿、阶段、节点及资源，发布冻结版本，归档与恢复路线。
- **社区发现**：搜索、难度筛选、排序、分页、路线详情和独立收藏。
- **个人学习**：恢复阅读位置、标记或撤销节点完成、每日打卡、打卡日历及连续天数。
- **版本升级**：预览版本差异，由学习者确认升级并处理节点完成状态，保留旧版学习历史。
- **社区交流**：路线话题、回复、处理状态、订阅更新与站内通知。
- **个人主页**：作品、动态、关注关系，以及受隐私设置控制的收藏与学习列表。
- **后台管理**：账号管理、官方路线维护、社区内容治理、举报处理、审计与系统信息。

当前代码仍保留整体就绪开关 `COMMUNITY_APPLICATION_READY = False`。上述模块已有实现，但不代表整个项目已完成最终验收。具体进度见上级目录的 `task_progress.md`；原 README 的阶段记录保留在 [README.history.md](README.history.md)，其中旧阶段说明不作为当前运行依据。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router、Axios |
| 后端 | Python 3.12、FastAPI、Pydantic 2、Uvicorn |
| 数据存储 | MySQL、SQLAlchemy 2 异步 ORM、asyncmy、Alembic |
| 认证 | JWT、Argon2 密码哈希、数据库会话管理 |
| 测试与检查 | pytest、Ruff、Vitest、Playwright、ESLint、vue-tsc |
| 依赖管理 | uv、pnpm，使用已提交的锁文件 |

站内通知通过应用内后台任务和数据库 outbox 处理，目前无需额外部署 Redis 或消息队列。

## 目录说明

| 路径 | 职责 |
| --- | --- |
| `backend/app/main.py` | FastAPI 应用入口 |
| `backend/app/routers/` | HTTP 接口；业务前缀 `/api/v1` |
| `backend/app/services/` | 业务处理 |
| `backend/app/domain/` | 账号和路线业务规则 |
| `backend/app/database/` | 数据连接、ORM 模型及数据访问 |
| `backend/app/schemas/` | 请求与响应模型 |
| `backend/app/core/` | 安全、异常、日志、中间件及限流 |
| `backend/app/config/` | 环境配置与枚举 |
| `backend/migrations/` | Alembic 数据库迁移 |
| `backend/scripts/` | 本地密钥配置和管理员创建工具 |
| `backend/tests/` | 后端测试 |
| `frontend/src/` | 页面、组件、路由、状态与接口调用 |
| `frontend/tests/` | 前端单元及浏览器测试 |

## 本地运行

以下命令以 **PowerShell** 为例，起始目录为本文件所在的 `Cognitrail`。若从外层项目目录开始，先执行 `Set-Location Cognitrail`。

### 1. 准备环境

- Python **3.12**（后端约束为 `>=3.12,<3.13`）。
- uv。
- Node.js **>=22.12.0**。
- pnpm **12.11.2**（见 `frontend/package.json`）。
- MySQL，当前默认基线为 **8.0.14**。

**MySQL 版本采用精确匹配，不是最低版本判断。** 迁移及健康检查会比较服务器版本与 `DB_REQUIRED_VERSION`。使用其他 MySQL 版本前应验证迁移、触发器和数据库测试，再配置实际版本，不能直接视为兼容。项目使用触发器落实部分数据库约束。

### 2. 配置后端

```powershell
Set-Location backend
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

编辑 `backend/.env` 中的本地数据库配置，再生成签名密钥：

```powershell
uv run python -m scripts.configure_auth
```

该脚本保留已有数据库配置，不输出密钥，也不会覆盖已有有效密钥。常用配置如下，完整选项见 [.env.example](backend/.env.example)。

| 配置项 | 用途 / 默认值 |
| --- | --- |
| `DB_HOST` / `DB_PORT` | 数据库地址 / `3306` |
| `DB_NAME` | 开发库，默认 `cognitrail_community` |
| `DB_USER` / `DB_PASSWORD` | 本地数据库凭证 |
| `DB_REQUIRED_VERSION` | 精确匹配的数据库版本，默认 `8.0.14` |
| `TEST_DB_NAME` | 独立测试库，需显式配置 |
| `JWT_SECRET` | 随机签名密钥，至少 32 字节 |
| `APP_TIMEZONE` | 业务时区，默认 `Asia/Shanghai` |
| `CORS_ORIGINS` | 允许的前端来源，JSON 数组 |
| `AVATAR_STORAGE_DIR` | 默认 `backend/.data/avatars` |
| `OUTBOX_ENABLED` | 是否启动通知后台任务，默认 `true` |

### 3. 创建数据库并迁移

先在 MySQL 客户端执行以下 SQL。应用和 Alembic **不负责创建数据库**。

```sql
CREATE DATABASE IF NOT EXISTS cognitrail_community
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cognitrail_community_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

数据库账号需有相应建表、迁移及创建触发器的权限。在 `backend` 目录执行：

```powershell
uv run alembic upgrade head
uv run alembic current
```

当前迁移链为 `c001_community` → `c002_notification_delete` → `c003_official_roadmaps` → `c004_topic_privacy` → `c005_resource_visits`。迁移会拒绝不兼容的旧库或不完整结构；新安装使用独立空库，不要通过 `stamp` 跳过结构校验。

### 4. 启动后端并创建管理员

仍在 `backend` 目录：

```powershell
uv run python -m scripts.create_admin --username local_admin --nickname 管理员
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers
```

管理员创建为首次使用时的可选步骤，密码通过交互输入，同名账号不会被覆盖。普通用户从前端注册；管理员参与普通社区操作时应使用另外的普通账号。

### 5. 启动前端

另开终端，进入 `Cognitrail/frontend`：

```powershell
pnpm install --frozen-lockfile
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
pnpm dev
```

默认通过 Vite 将 `/api` 和 `/health` 代理至 `http://127.0.0.1:8000`。调整后端端口时，同时修改前端 `.env` 的 `VITE_API_PROXY_TARGET`。

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:5173 | 前端 |
| http://127.0.0.1:8000/docs | Swagger 接口文档 |
| http://127.0.0.1:8000/health/live | 进程存活检查，不访问数据库 |
| http://127.0.0.1:8000/health/ready | 数据库、迁移和整体业务就绪检查 |

当前整体就绪开关为关闭状态，即使数据库正常，`/health/ready` 仍会返回 `503 COMMUNITY_REFACTOR_PENDING`；应结合错误码区分数据库故障与整体尚未就绪。

## 测试与代码检查

以下命令依据项目配置整理；本次 README 整理未重新执行应用启动或完整测试，不沿用历史通过数量作为当前验证结果。

### 后端

在 `backend` 目录执行离线单元测试和静态检查：

```powershell
uv run pytest tests/unit -m "not database"
uv run ruff check .
uv run ruff format --check .
```

真实数据库测试需使用独立测试库。先在单独终端中迁移测试库，避免影响日常启动环境：

```powershell
# 当前目录：backend；仅在这个终端临时切换迁移目标。
$env:DB_NAME = 'cognitrail_community_test'
uv run alembic upgrade head
Remove-Item Env:DB_NAME

# 测试通过 TEST_DB_NAME 选择测试库，DB_NAME 仍应为开发库。
$env:TEST_DB_NAME = 'cognitrail_community_test'
$env:RUN_DB_TESTS = '1'
uv run pytest
Remove-Item Env:RUN_DB_TESTS
Remove-Item Env:TEST_DB_NAME
```

测试会写入并清理数据，不使用开发库或生产库。允许的测试库名称为 `cognitrail_community_test`，或追加下划线分隔的字母数字后缀。部分历史用例仍被隔离或跳过，应查看实际测试输出。

### 前端

在 `frontend` 目录：

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

浏览器测试要求测试库已迁移且后端 `.env` 中数据库连接与 JWT 配置可用：

```powershell
$env:TEST_DB_NAME = 'cognitrail_community_test'
pnpm test:e2e
Remove-Item Env:TEST_DB_NAME
```

Playwright 自动启动独立后端 `18000` 和前端 `15173`，不会复用已运行的开发服务。Windows 默认使用已安装的 Microsoft Edge。如需使用 Playwright Chromium，可在执行测试前运行：

```powershell
pnpm exec playwright install chromium
$env:PLAYWRIGHT_CHANNEL = 'chromium'
```

端口可通过 `E2E_BACKEND_PORT`、`E2E_FRONTEND_PORT` 调整。报告与截图位于 `frontend/test-results/` 等测试产物目录，不提交到仓库。

## 使用与部署说明

- 登录凭证保存在前端内存，刷新页面需要重新登录。修改密码、停用账号或管理员重置会撤销相关会话。
- 修改工作稿不改变已发布快照；学习者是否升级到新版由本人确认，不自动覆盖旧版进度。
- 收藏、关注、开始学习及更新订阅是独立操作。
- 打卡按北京时间计算，同日多路线打卡在累计天数中合并为一天；节点完成不自动产生打卡。
- 头像文件位于 `backend/.data/avatars`，部署时需持久化并与数据库一起备份。
- `pnpm build` 生成 `frontend/dist/`。生产部署需配置静态服务、SPA 路由回退及 `/api`、`/health` 反向代理；Vite 开发代理不会包含在构建产物中。
- `pnpm preview` 只用于预览静态构建，不代表完整生产部署；访问 API 仍需正确的地址或代理配置。

## Git 提交约定

`.gitignore` 已排除真实 `.env`、Python 虚拟环境、`node_modules`、构建产物、缓存、日志、上传数据和测试报告。应提交 `.env.example`、`uv.lock`、`pnpm-lock.yaml`、源码、测试代码及 Alembic 迁移文件。

忽略规则不会自动取消 Git 已跟踪的文件；提交前检查 `git status`。当前说明不包含可直接登录的预置密码。
