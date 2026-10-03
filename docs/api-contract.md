# 服务契约核对记录

2026-10-04 读取 https://ccqwell.vip.cpolar.cn/docs 与 /openapi.json，核对服务仓库提交 dfc4e7efe5f9353aec969dbee2100eb1f67a121d。

采用公开 REST 的输入规范化、异步 jobs、SSE、身份/额度/历史、认证产物下载。没有 REST 取消或提交幂等键。MCP 的幂等、安全分块、元数据等不能当作 REST 能力。CLI 没有复制网页 Cookie 管理操作。

手写文档中的最小直井 YAML 缺开次；CONTEXT、YAML 指南及校验器要求 0° 直井存在 holeSections。文档宣称 wellInfo 必填，但地层/钻井液独立区块实际受支持。模板使用服务 static/examples，全部经目标服务 normalize 复核。完整 YAML B 点 auto/null 垂深遵循 ADR-0097，严格 JSON 不扩展。

下载以 archive_id 为准，未设置才用 id；job 状态有界且重启丢失，历史产物可能仍在，但套餐历史清理或部署清理会删除。非 2xx 的 problem 与终态嵌套 error 均需保留 traceId/errors。等待超时不意味着服务停止。
