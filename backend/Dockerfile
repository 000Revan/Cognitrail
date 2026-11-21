FROM python:3.12-slim

# 从 uv 官方镜像中复制 uv 工具
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 不生成字节码；及时输出控制台日志
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 使用基础镜像的 Python，不额外下载解释器
ENV UV_PYTHON_DOWNLOADS=never

# 让 uvicorn、alembic 等命令使用虚拟环境中的版本
ENV PATH="/app/.venv/bin:$PATH"

# 先安装依赖，便于修改源码时复用这一层缓存
COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev --no-install-project --python /usr/local/bin/python --no-cache

# 复制 .dockerignore 筛选后保留的项目文件
COPY . .


EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]