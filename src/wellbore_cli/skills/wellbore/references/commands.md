# 命令选择

## 通用规则

`wellbore COMMAND --help` 提供当前版本帮助。通用参数可放根命令或叶子命令：`--json`、`--base-url`、`--key-file`、`--timeout`、`--no-proxy`。用 JSON 字段处理返回值，勿从 stderr 进度提取结构化状态。
普通 stdout 为一份 JSON；`jobs events --json` 为 JSON Lines。输入支持 .yaml/.yml/.json，`-` 表示 stdin，需 `--input-format yaml|json`，最大 1 MiB。

## 一次出图

```sh
wellbore validate well.yaml --json
wellbore render well.yaml --image-format png -o output --json
```

render 默认预校验、提交一次、轮询、下载文件清单及规范化输入。`--wait-timeout` 默认 180 秒，`--interval` 默认 1 秒，单次请求 `--timeout` 默认 30 秒。所有值须大于零且有限。
产物放在 `output/<archive_id>/`，不覆盖已有文件。`--skip-validation` 省略预校验，仍会由渲染器校验，但坏输入可能已消耗额度，通常不用。

## 分步和批处理

```sh
wellbore jobs submit well.yaml --image-format svg --name '项目名称' --json
wellbore jobs status JOB_ID --json
wellbore jobs wait JOB_ID --wait-timeout 300 --json
wellbore jobs events JOB_ID --wait-timeout 300 --json
```

从 submit 返回值保留 id，等待不会创建新任务。SSE 只跟现有任务，终态后关闭；流中断改用 wait 查询，不重新 submit。不支持 CLI 批量服务提交命令；脚本逐个提交、每次保留 ID，避免失控并发和额度浪费。

## 输入、历史与产物

```sh
wellbore template horizontal -o well.yaml
wellbore normalize well.yaml -o normalized.json --json
wellbore history --json
wellbore download ARCHIVE_ID --file well_structure_plot.png -o figure.png --json
wellbore download ARCHIVE_ID --file well_data.yaml -o normalized.yaml --json
wellbore download ARCHIVE_ID -o archive.zip --json
```

normalize 的 stdout 或输出文件是完整 JSON。规范化 YAML 下载可能以 JSON 文本表达（JSON 是 YAML 子集），无需“修复”格式。ZIP 不自动解压。下载支持单文件原子写入，不支持断点续传或自动缓存协议；断线后重新下载整个所选文件。
产物清单由实际返回决定，不能假定所有 CSV 都存在。SVG/PNG 格式在提交时决定，下载不转换格式。

## 更新现有历史

```sh
wellbore render revised.yaml --edit ARCHIVE_ID --name '修订井' -o revised-output --json
```

edit 成功后更新选定历史，不一定新建记录。下载使用状态的 archive_id，空时才回退 id。此命令修改远程历史且消耗绘图额度，必须属于用户要求的修改范围。客户端不提供收藏、删除、复制项目、管理账户或 API Key 等网页会话操作。

## 退出码

0 成功；1 HTTP/服务问题；2 用法/本地文件/输入；3 凭据；4 网络/等待超时；5 failed/cancelled；130 中断。
`jobs status` 查询到 failed 也返回 5 并保留完整快照；不要只检查 HTTP 状态。渲染失败保留 error、traceId、errors。用法错误由 argparse 提示，不保证 stderr 为 JSON。
