# wellbore

井身结构图服务的轻量客户端。Python 3.11+，运行时零第三方依赖，无需安装 matplotlib、字体或服务端代码。内置中文命令帮助、YAML 模板和按需加载的 Codex skill。

## 安装

推荐用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 安装隔离的命令行工具：

```sh
uv tool install --python 3.11 'git+https://github.com/elf004-star/drilling-agent-skills.git'
wellbore --help
```

此 Git 安装方式需先将本仓库当前实现推送至远端。当前本地立即可用：

```sh
uv tool install --python 3.11 .
# 或不全局安装
uv run --python 3.11 wellbore --help
```

也支持 `pipx install .` 或 `pip install .`。发布 wheel 后支持 `uv tool install /path/to/wellbore_cli-0.1.0-py3-none-any.whl`。当前未发布到 PyPI，不使用不存在的索引安装命令。

## 五分钟上手

```sh
wellbore auth set                     # 隐藏输入 API Key，本机保存
wellbore health
wellbore quota
wellbore template straight -o well.yaml
# 编辑 well.yaml，替换示例井数据
wellbore validate well.yaml
wellbore render well.yaml -o output
```

输出保存到 `output/<archive_id>/`，包括图片、服务实际生成的 CSV 等文件和规范化输入 `well_data.yaml`。保留服务 warnings；不要把示例数据当作用户的实际井数据。

临时密钥推荐通过 `WELLBORE_API_KEY` 环境变量或 `--key-file /path/to/key` 传入。避免把密钥直接写在命令行、URL、脚本或仓库。`auth clear` 仅删除本机存储；撤销 Key 在服务网页完成。POSIX 保存文件权限为 0600；Windows 应使用受保护的用户配置目录。

基地址默认 `https://ccqwell.vip.cpolar.cn`，可运行 `wellbore config set-url https://your-service.example`。优先级：`--base-url` > `WELLBORE_BASE_URL` > 配置 > 默认值；密钥优先级：显式 `--key-file` > `WELLBORE_API_KEY` > 保存文件。`WELLBORE_CONFIG_DIR` 可隔离多个使用环境。

## 分步操作与脚本

```sh
wellbore normalize well.yaml -o normalized.json
wellbore jobs submit well.yaml --image-format svg --json
wellbore jobs status JOB_ID --json
wellbore jobs wait JOB_ID --wait-timeout 300 --json
wellbore jobs events JOB_ID --json       # JSON Lines，每行一个完整快照
wellbore history --json
wellbore download ARCHIVE_ID --file well_structure_plot.svg -o figure.svg
wellbore download ARCHIVE_ID -o archive.zip
wellbore render well.yaml --edit ARCHIVE_ID --name '测试井' -o output
cat well.yaml | wellbore validate - --input-format yaml --json
```

所有命令支持 `--json`、`--base-url`、`--key-file`、`--timeout`、`--no-proxy`。普通命令的 stdout 是单份 JSON；进度和错误走 stderr；模板与 normalize 可直接输出输入文本。`jobs events --json` 为 JSON Lines。现有文件默认拒绝覆盖，显式 `--force` 才替换；下载按文件原子落盘，中断不留下半份最终文件。不自动解压 ZIP。

退出码：0 成功，1 HTTP/服务问题，2 用法/本地输入/文件问题，3 凭据问题，4 网络/客户端等待超时，5 任务 failed/cancelled，130 用户中断。查询成功但任务失败也退出 5。argparse 用法错误使用标准 stderr 提示。

REST 提交没有幂等键：客户端不会自动重试提交。POST 超时或断连后先查 `history`，避免重复绘图与扣额度。已知 ID 的任务可用 `jobs wait` 恢复；任务状态 404 可能是服务重启/状态淘汰，先检查历史。等待超时/中断不会取消服务端任务。HTTP 仅允许 localhost 开发，重定向被拒绝以避免转发密钥。

代理遵循系统/环境配置，HTTPS 使用 `HTTPS_PROXY`；如果本机旧代理不可用，用 `--no-proxy`。本地可用代理示例为 `http://127.0.0.1:8118`。标准库传输不直接支持 SOCKS。

## 安装 skill

```sh
wellbore skill install
# 指定其他技能根目录
wellbore skill install --dir /path/to/skills
wellbore skill path
```

安装复制到 `<dir>/wellbore`，已有目录拒绝覆盖。重新加载技能后调用 `$wellbore`。仓库入口为 [skills/wellbore/SKILL.md](skills/wellbore/SKILL.md)，`skills` 是指向随 wheel 打包的源文件目录的相对符号链接；源码唯一来源位于 `src/wellbore_cli/skills`。技能只按任务需要加载安装、命令、领域、恢复与 API 边界参考。

## 开发与验证

```sh
uv run --python 3.11 python -m unittest discover -s tests -v
uv build
```

详见 [架构说明](docs/architecture.md)、[领域上下文](CONTEXT.md) 和 [契约快照](docs/api-contract.md)。线上来源为 [API 文档](https://ccqwell.vip.cpolar.cn/docs) 与 `/openapi.json`。不提供需要网页会话的注册、账户管理、Key 管理或管理员命令；REST 文档没有公开取消端点，因此不伪造取消命令。
