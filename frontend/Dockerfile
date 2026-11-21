# 第一阶段：构建前端
FROM node:24-bookworm-slim AS builder

WORKDIR /app

# 安装与项目 package.json 一致的 pnpm 版本
RUN npm install --global pnpm@12.11.2

# 先复制依赖配置，便于复用依赖安装缓存
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

RUN pnpm install --frozen-lockfile

# 复制 .dockerignore 筛选后保留的源码和配置
COPY . .

# 执行类型检查并打包，生成 /app/dist
RUN pnpm build

# 第二阶段：运行网页服务
FROM nginx:stable-alpine

# 使用项目自己的 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 只复制第一阶段的打包结果
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]