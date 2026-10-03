# REST 契约与边界

核对日期：2026-10-04（北京时间）。来源：[线上手写文档](https://ccqwell.vip.cpolar.cn/docs)、[OpenAPI](https://ccqwell.vip.cpolar.cn/openapi.json)，以及服务源码提交 dfc4e7efe5f9353aec969dbee2100eb1f67a121d。若服务升级，以线上校验与实际响应为准；文档文字与领域源码不一致时不猜测字段。

| CLI | REST | 认证 |
|---|---|---|
| health | GET /api/health | 无 |
| validate / normalize | POST /api/input/normalize，YAML/JSON 原始 body | 无 |
| render / jobs submit | POST /api/jobs?image_format=png 或 svg；可带 edit/project_name | Bearer |
| jobs status / wait | GET /api/jobs/{id} | 源码公开，CLI 为一致性携带 Bearer |
| jobs events | GET /api/jobs/{id}/events | 同上 |
| account | GET /api/account | Bearer |
| quota | GET /api/account/quota | Bearer |
| history | GET /api/account/artifacts，裸数组 | Bearer |
| download | GET /api/renders/{archive_id}/{name} 或 {archive_id}.zip | Bearer，创建者 |

submit 返回 202 快照；字段包括 id、archive_id、status、warnings、files（name/bytes）、error。
状态为 queued/running/success/failed/cancelled。GET failed 仍是 200，error 内保存 problem。SSE event 名 status，data 为同形快照；终态后关闭，不做重放。
normalize 返回完整输入 JSON，不创建任务不占绘图额度。REST submit 的领域校验可在异步渲染中失败，所以默认 render 先 normalize。
非 2xx 使用 application/problem+json，字段包括 type/title/status/detail/instance/traceId/errors。

不实现网页会话限定的注册/登录、资料编辑、密码、Key 管理、历史永久删除、收藏、管理员功能。无需拿测试 Key 尝试这些端点。源代码 MCP 层的幂等键、取消、元数据、分块/预览工具不是公开 REST CLI 能力，不能直接宣称支持。

签名主图 URL 可供分享但有短期有效期，CLI 通过认证路径下载，不保存/输出签名 URL。下载客户端不跨重定向转发密钥；产物名必须是单个路径名称。
