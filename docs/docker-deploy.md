# Docker 部署

## 直接拉取 Docker Hub 镜像运行

```bash
git clone <your-repo-url> chatgpt2api
cd chatgpt2api
docker compose up -d
```

默认会拉取 Docker Hub 镜像：

```text
qing8895/chatgpt2api:latest
```

服务地址：

```text
http://localhost:3000
```

数据和配置通过宿主机挂载保留：

```text
./data:/app/data
./config.json:/app/config.json
```

## 后续升级镜像

镜像发布后，服务器上直接拉取新镜像并替换容器：

```bash
docker compose pull
docker compose up -d
docker image prune -f
```

## 本地构建并推送 Docker Hub

需要先登录 Docker Hub：

```bash
docker login
```

单架构构建并推送：

```bash
docker build -t qing8895/chatgpt2api:latest .
docker push qing8895/chatgpt2api:latest
```

多架构构建并推送：

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t qing8895/chatgpt2api:latest --push .
```

## GitHub Actions 自动发布

仓库已经配置 `.github/workflows/docker-publish.yml`。在 GitHub 仓库设置里添加两个 Secrets：

```text
DOCKERHUB_USERNAME=qing8895
DOCKERHUB_TOKEN=<Docker Hub access token>
```

然后手动触发 `Publish Docker Image`，或推送 `v*` tag：

```bash
git tag v1.0.0
git push origin v1.0.0
```

## 本地源码构建运行

如果不想拉 Docker Hub 镜像，也可以直接本地构建：

```bash
docker compose -f docker-compose.build.yml up -d --build
```
