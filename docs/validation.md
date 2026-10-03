# 验证记录

日期：2026-10-04，北京时间。

- 本机标准库 HTTP 集成测试：18 项通过。覆盖授权/公开预检、原文输入与参数、无效输入阻止提交、失败终态退出码、archive_id 下载、SSE 关闭/中断、有界等待、重定向拒绝、文件原子写入/覆盖、配置优先级/权限、跨平台路径/体积限制、离线 skill 与模板、未知 POST 结果不重试、显式密钥文件脱敏。
- skill-creator quick_validate 通过；独立代理仅获 skill 路径和“地层+钻井液、未知提交结果恢复”用户请求，离线完成有效结构与命令选择，正确保留双栏垂深、未补占位井、未自动重发未知 POST。
- 线上 health、身份和 quota 可用；六个模板均通过公开 normalize，straight 规范化结果再以严格 JSON 提交 normalize，一致。
- 用用户提供的测试 Key 生成直井 PNG 和水平井 SVG，均 success、warnings 为空，各下载 15 项文件（含规范化输入），图片格式标识有效。SSE 终态返回一次快照并关闭，PNG 全量 ZIP 完整性通过。共用 2 次测试绘图额度，未执行账户/管理员操作。
- 任务 ID：PNG ddb33a56-b5dd-41c4-9503-b627a7b7863e；SVG f53f0bc4-45e2-4157-b390-ef31d4f55691。测试产物保存于本机 /private/tmp/wellbore-live-output，未加入版本库；线上历史可能按服务清理规则消失。
- 已构建 wheel 与 sdist；wheel 包含全部 skill 参考与六份资产，无运行时依赖。在临时隔离工具目录实际安装 wheel，验证版本、离线模板与 skill 安装；源码 uv run 入口也已验证。主图 PNG 已做视觉检查。

线上测试不是单元测试的一部分，不在 CI 使用密钥或消耗额度。CI 配置覆盖 Linux/macOS/Windows；当前本机运行证据仅 macOS，其他平台需远端 CI 执行后确认。GitHub Actions 尚未执行。未发布到 PyPI，也未自动推送源码。
