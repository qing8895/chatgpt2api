Sentinel 使用独立、常驻、匿名 Chromium 服务。浏览器直接采集 25 字段 p，主服务从同一个 p 的环境字段计算 FNV-1a 32 位 + avalanche PoW（带 `~S`），再提交 `prepare_token`、`proofofwork`、`turnstile` 完成 finalize。

solver HTTP 接口只接受 p、dx；未知字段会被拒绝。账号 token、Cookie、用户 prompt 不进入 solver。所有端点使用 `SENTINEL_SOLVER_KEY` 鉴权，Compose 不映射 solver 端口到宿主机。挑战在真实 chatgpt.com 匿名页面的当前 Turnstile 模块里执行；模块变化或挑战失败时明确报错，不回退到模拟浏览器。

Chromium 通过 Xvfb 常驻运行，浏览器采集值同时用于 p 和主服务请求头。Compose 的 `init: true` 负责子进程和 Xvfb 信号处理，主服务与 solver 均配置就绪检查。

部署前在 `.env` 配置：

```dotenv
SENTINEL_SOLVER_KEY=<随机私有密钥>
SENTINEL_SOLVER_TIMEZONE=<实际出口对应的 IANA 时区>
SENTINEL_SOLVER_PROXY=<和主服务一致的出口代理；直连时留空>
```

检查代理出口可使用 `curl -x <代理地址> https://ipwho.is/` 的 `timezone.id`；直连时不加 `-x`。账号单独配置代理时，也必须与常驻 solver 的出口一致。WARP 部署的 solver 代理通常应设为 `http://privoxy:8118`，需在 WARP 启动后检查其实际出口时区。

```sh
docker compose -f docker-compose.local.yml up -d --build
```

实际图片会话 `POST /backend-api/f/conversation` 仅在 model 为 `auto`、HTTP 404、JSON `detail` 精确等于 `Model not found` 时换号。失败账号仅在进程内冷却 600 秒，与轮询失败共享原有的 4 次换号重试预算。额度、永久状态和代理评分不因该错误改变。进程重启后本地冷却消失。

验收主服务需有可用账号和真实额度。运行：

```sh
export CHATGPT2API_AUTH_KEY='<主服务 API 密钥>'
python scripts/verify_image_generation.py --url http://127.0.0.1:8000
```

脚本分别请求文生图和图生图，下载返回图片，使用 Pillow `load()` 完整解码，保存 PNG 和 `data/acceptance/report.json`。只有两项均成功才退出 0。握手成功、SSE HTTP 200 均不构成图片验收成功。

常驻页面的模块发现和 WeakMap 绑定方式参考 [MEIZU16/chatgpt2api](https://github.com/MEIZU16/chatgpt2api/tree/main/sentinel_solver)。其 SHA3 PoW 未被采用。
