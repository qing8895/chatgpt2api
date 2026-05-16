# External Image API

面向外部系统的轻量图片生成接口。认证方式与管理端一致，使用：

```http
Authorization: Bearer <auth-key>
```

## 同步生成

`POST /api/external/images/generations`

请求：

```json
{
  "prompt": "一只玻璃质感的未来感猫头鹰，白底产品海报",
  "model": "gpt-image-2",
  "size": "1:1",
  "n": 1,
  "response_format": "url"
}
```

返回：

```json
{
  "ok": true,
  "mode": "sync",
  "created": 1760000000,
  "data": [
    {
      "url": "https://your-domain.com/images/2026/05/16/xxx.png",
      "revised_prompt": "..."
    }
  ]
}
```

curl：

```bash
curl -X POST "http://localhost:3000/api/external/images/generations" \
  -H "Authorization: Bearer <auth-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "一只玻璃质感的未来感猫头鹰，白底产品海报",
    "model": "gpt-image-2",
    "size": "1:1",
    "n": 1,
    "response_format": "url"
  }'
```

## 异步任务

账号较多或外部调用方不适合长连接等待时，可以传 `async_mode: true`。接口会立即返回任务 ID，随后调用已有任务查询接口轮询。

创建任务：

```json
{
  "prompt": "赛博朋克城市夜景",
  "model": "gpt-image-2",
  "size": "16:9",
  "n": 2,
  "async_mode": true,
  "client_task_id": "order-10001"
}
```

查询任务：

```bash
curl "http://localhost:3000/api/image-tasks?ids=order-10001,order-10001-2" \
  -H "Authorization: Bearer <auth-key>"
```

任务成功后，`data[0].url` 即为图片地址。
