# 安装与认证

以下示例默认 POSIX shell；PowerShell/cmd 请按本机 shell 调整路径、引号和环境变量写法（`$VAR` ↔ `$env:VAR` / `%VAR%`）。

## 安装 CLI

本机源码（把 `<repo>` 换成实际路径；路径有空格时加引号；Windows 用 `C:\...`）：

```sh
uv tool install --python 3.11 "<repo>"
wellbore --version
```

代码已推送远端时：

```sh
uv tool install --python 3.11 "git+https://github.com/elf004-star/drilling-agent-skills.git"
```

CLI 需要 Python 3.11+，运行时无第三方依赖。未发布到 PyPI 时不要使用索引名称安装。
在源码目录也可运行 `uv run --python 3.11 wellbore --help`。不要安装服务端绘图栈。

## 密钥与基地址

要求用户在终端交互执行 `wellbore auth set`，输入隐藏。POSIX 保存文件权限为 0600；Windows 上 Python 不额外设置 ACL，文件位于用户配置目录（默认 `C:\Users\<user>\.config\wellbore`），请确保该目录仅本人可读。更稳妥的做法是用环境变量，或把 `--key-file` 放在受 ACL 限制的目录。已有密钥可使用 `WELLBORE_API_KEY` 或 `--key-file`；不要把明文放到参数、URL 或聊天中。检查 `wellbore auth status --json`，不显示密钥。

默认服务为 `https://ccqwell.vip.cpolar.cn`。优先级：`--base-url` > `WELLBORE_BASE_URL` > 本机配置 > 默认；`--key-file` > 环境密钥 > 保存文件。配置目录由 `WELLBORE_CONFIG_DIR` 或 `XDG_CONFIG_HOME` 下的 `wellbore` 确定（默认 `~/.config/wellbore`；Windows 默认 `C:\Users\<user>\.config\wellbore`）。

```sh
wellbore config set-url https://service.example
wellbore config show --json
wellbore health --json
wellbore quota --json
```

`auth clear` 不撤销服务端 Key，环境密钥也不会被删除。更换/撤销 Key 在服务 `/keys` 网页完成。
`health` 无需密钥，不能证明账户有绘图权限；`quota` 读取实时额度，勿硬编码套餐数字。

## 代理与 HTTPS

网络请求遵循环境代理。代理不可用时加 `--no-proxy`；有可用本地 HTTP 代理时可设置 `HTTPS_PROXY` 环境变量（PowerShell：`$env:HTTPS_PROXY=...`；cmd：`set HTTPS_PROXY=...`）。CLI 不直接支持 SOCKS，需使用 HTTP 代理。
远程只允许 HTTPS；本机 localhost/127.0.0.1/::1 可使用 HTTP。重定向被拒绝，不能绕过该限制转发密钥。

## skill 安装

```sh
wellbore skill install --dir ~/.claude/skills        # Claude Code
wellbore skill install                               # Codex 默认目录
wellbore skill install --dir <skills-dir>            # 其他技能根目录
```

复制至 `<dir>/wellbore`，已有目录拒绝覆盖。Claude Code 的 Windows 路径是 `--dir "%USERPROFILE%\.claude\skills"`。Codex 默认技能根目录为 `CODEX_HOME/skills`，未设置时为 `~/.codex/skills`。更新时先审阅已有技能，再选择新目录或自行替换。
