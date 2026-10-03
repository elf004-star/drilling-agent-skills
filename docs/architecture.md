# CLI 与 skill 架构

`cli.py` 负责命令发现、工作流编排和输出；`client.py` 负责 REST 与任务生命周期；`config.py` 负责地址/密钥优先级与本机存储；`files.py` 负责有界输入、文件名安全与原子落盘；`errors.py` 负责稳定退出码与 problem 数据。

客户端只使用 Python 标准库，安装不带绘图栈，读取 YAML 原文并按正确 Content-Type 发送。不解析 YAML、不复制服务端 schema、不自行推导领域数量。render 先 normalize 预检，仍提交原输入，保留服务对短写的解释与 warnings。

HTTP POST 永不自动重试；GET 查询也保持显式简单轮询，等待有单独总时限。SSE 提供分步观测，收到终态即关流，断线给出同 ID 恢复入口。CLI 不虚构 REST 取消、幂等键或 MCP 工具。

下载按 64 KiB 流式传输，临时文件与目标同目录，完成后原子发布。已有文件默认拒绝覆盖，并用独占发布保护并发写入；--force 替换目标路径而不改写其符号链接指向的文件。批量产物是逐文件原子操作，不是整目录事务，失败后已完成文件保留，按清单补取。

skill 的三级披露：frontmatter 用于触发；SKILL.md 为简短核心流程与路由；references 按安装、领域、命令、恢复、API 边界分工，assets 保存六个服务案例。资源随 wheel 打包，CLI 的 skill install 安装完全相同的文件。根目录 skills 是源码目录符号链接，避免两份文档漂移。

验证使用标准库 unittest：本地 HTTP 测试覆盖真实传输、授权、重定向、失败终态、SSE、输入映射、文件保护；线上测试只读健康/账户/额度、无额度预检和少量完整渲染。密钥不作为 fixture、不落入仓库。另用独立代理按 skill 完成离线场景，验证导航和安全边界。
