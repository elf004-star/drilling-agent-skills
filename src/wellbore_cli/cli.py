"""Command discovery and presentation, separate from transport and file IO."""
import argparse
import getpass
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import shutil
import sys

from . import __version__
from .client import Client, segment
from .config import config_dir, load, private_write, resolve, validate_url
from .errors import ClientError
from .files import atomic_save, read_input, safe_name

SKILL = files("wellbore_cli").joinpath("skills", "wellbore")


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("必须是大于零的有限数值")
    return number


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base-url", default=argparse.SUPPRESS, help="覆盖服务基地址")
    common.add_argument("--key-file", default=argparse.SUPPRESS, help="从文件读取密钥（不放入命令行）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="标准输出为 JSON；错误为 stderr JSON")
    common.add_argument("--timeout", type=positive, default=argparse.SUPPRESS, help="单次请求超时秒数（默认 30）")
    common.add_argument("--no-proxy", action="store_true", default=argparse.SUPPRESS, help="忽略环境代理")
    p = argparse.ArgumentParser(prog="wellbore", parents=[common], description="井身结构图 REST 客户端：校验、生成、等待、下载。",
                                epilog="首次使用：template straight -o well.yaml → validate well.yaml → render well.yaml -o output")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)

    def leaf(group, name, help):
        return group.add_parser(name, help=help, description=help, parents=[common])

    def input_args(c):
        c.add_argument("input", help="YAML/JSON 文件，或 - 表示 stdin")
        c.add_argument("--input-format", choices=["yaml", "json"], help="显式输入格式（stdin 必填）")

    def submit_args(c):
        input_args(c)
        c.add_argument("--image-format", choices=["png", "svg"], default="png")
        c.add_argument("--name", help="项目名称（最多 100 字）")
        c.add_argument("--edit", help="成功后更新此历史 ID；下载采用返回的 archive_id")

    def wait_args(c):
        c.add_argument("--wait-timeout", type=positive, default=180, help="等待终态秒数；超时不取消任务")
        c.add_argument("--interval", type=positive, default=1, help="轮询间隔秒数")

    leaf(commands, "health", "检查服务存活（无需密钥）")
    leaf(commands, "account", "读取当前身份")
    leaf(commands, "quota", "读取服务实际额度与重置时间")
    leaf(commands, "history", "列出自己的历史与现有产物")
    c = leaf(commands, "validate", "服务端编译校验，不创建任务、不消耗绘图额度")
    input_args(c)
    c = leaf(commands, "normalize", "将服务端规范化 JSON 输出到 stdout 或文件")
    input_args(c)
    c.add_argument("-o", "--output")
    c.add_argument("--force", action="store_true")
    c = leaf(commands, "render", "一次完成校验、提交、等待并下载产物")
    submit_args(c)
    wait_args(c)
    c.add_argument("-o", "--output", default="wellbore-output", help="输出目录；默认按 archive_id 再分目录")
    c.add_argument("--force", action="store_true")
    c.add_argument("--skip-validation", action="store_true", help="跳过预校验（渲染仍由服务校验，可能消耗额度）")
    c = leaf(commands, "download", "按历史/产物 ID 下载；无需任务状态仍在内存")
    c.add_argument("archive_id")
    c.add_argument("--file", default="zip", help="产物名称，默认 zip（下载全部，不自动解压）")
    c.add_argument("-o", "--output", help="目标文件路径")
    c.add_argument("--force", action="store_true")
    c = leaf(commands, "template", "输出经过服务校验的 YAML 模板（无需联网）")
    c.add_argument("name", choices=["straight", "horizontal", "deviated", "updip", "liner", "geology"])
    c.add_argument("-o", "--output")
    c.add_argument("--force", action="store_true")
    jobs = leaf(commands, "jobs", "分步提交、查询、等待与 SSE 事件流").add_subparsers(dest="action", required=True)
    c = leaf(jobs, "submit", "只提交一次，返回任务快照；不自动重试")
    submit_args(c)
    c = leaf(jobs, "status", "查询任务当前快照")
    c.add_argument("job_id")
    c = leaf(jobs, "wait", "等待现有任务终态，失败以非零退出")
    c.add_argument("job_id")
    wait_args(c)
    c = leaf(jobs, "events", "跟踪 SSE；终态立即关闭；--json 输出 JSON Lines")
    c.add_argument("job_id")
    c.add_argument("--wait-timeout", type=positive, default=180)
    auth = leaf(commands, "auth", "本机密钥存储；不管理服务端 API Key").add_subparsers(dest="action", required=True)
    c = leaf(auth, "set", "交互隐藏输入密钥并保存（POSIX 权限 0600）")
    c.add_argument("--stdin", action="store_true", help="从标准输入读取密钥")
    leaf(auth, "status", "显示密钥是否已配置，不显示内容")
    leaf(auth, "clear", "删除本机保存的密钥（不撤销服务端 Key）")
    cfg = leaf(commands, "config", "服务地址与本机配置").add_subparsers(dest="action", required=True)
    leaf(cfg, "show", "显示生效的地址和配置目录，不显示密钥")
    c = leaf(cfg, "set-url", "保存 HTTPS 基地址；本机开发允许 HTTP")
    c.add_argument("url")
    sk = leaf(commands, "skill", "查看或安装随 CLI 分发的 skill").add_subparsers(dest="action", required=True)
    leaf(sk, "path", "显示内置 skill 位置")
    c = leaf(sk, "install", "将内置 skill 复制到指定技能目录，拒绝覆盖")
    c.add_argument("--dir", default=str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills"))
    return p


def emit(value, machine=False):
    # Keep structured responses intact; human prose goes to stderr.
    print(json.dumps(value, ensure_ascii=False, indent=None if machine else 2))


def terminal_code(status):
    if status.get("status") in ("failed", "cancelled"):
        return 5
    return 0


def progress(value):
    print(f"任务 {value['id']}: {value['status']}", file=sys.stderr)


def local_command(args, machine):
    if args.command == "template":
        data = SKILL.joinpath("assets", args.name + ".yaml").read_bytes()
        if args.output:
            emit(atomic_save(args.output, [data], args.force), machine)
        elif machine:
            emit({"name": args.name, "yaml": data.decode("utf-8")}, True)
        else:
            sys.stdout.write(data.decode("utf-8"))
    elif args.command == "skill":
        if args.action == "path":
            emit({"path": str(SKILL)}, machine)
        else:
            destination = Path(args.dir).expanduser() / "wellbore"
            if destination.exists():
                raise ClientError("skill 目录已存在；先检查已有版本，再选择新目录", 2)
            shutil.copytree(str(SKILL), destination)
            emit({"path": str(destination.resolve())}, machine)
    elif args.command == "auth":
        path = config_dir() / "api-key"
        if args.action == "set":
            secret = sys.stdin.readline().strip() if args.stdin else getpass.getpass("API Key: ").strip()
            if not secret or any(c.isspace() for c in secret):
                raise ClientError("密钥不能为空或包含空白", 2)
            private_write(path, secret + "\n")
            emit({"saved": True, "path": str(path)}, machine)
        elif args.action == "clear":
            path.unlink(missing_ok=True)
            emit({"cleared": True, "environment_key_present": bool(os.environ.get("WELLBORE_API_KEY"))}, machine)
        else:
            _, key = resolve(getattr(args, "base_url", None), getattr(args, "key_file", None))
            emit({"configured": bool(key), "stored_key_present": path.exists(),
                  "environment_key_present": bool(os.environ.get("WELLBORE_API_KEY"))}, machine)
    elif args.command == "config":
        if args.action == "set-url":
            base = validate_url(args.url)
            settings = load()
            settings["base_url"] = base
            private_write(config_dir() / "config.json", json.dumps(settings) + "\n")
        else:
            base, _ = resolve(getattr(args, "base_url", None), getattr(args, "key_file", None))
        emit({"base_url": base, "config_dir": str(config_dir())}, machine)
    else:
        return False
    return True


def run(args):
    machine = getattr(args, "json", False)
    if local_command(args, machine):
        return 0
    base, key = resolve(getattr(args, "base_url", None), getattr(args, "key_file", None))
    client = Client(base, key, getattr(args, "timeout", 30), getattr(args, "no_proxy", False))
    paths = {"health": "/api/health", "account": "/api/account", "quota": "/api/account/quota",
             "history": "/api/account/artifacts"}
    if args.command in paths:
        emit(client.request("GET", paths[args.command], auth=args.command != "health"), machine)
    elif args.command in ("validate", "normalize", "render") or (args.command == "jobs" and args.action == "submit"):
        body, media = read_input(args.input, args.input_format)
        if args.command in ("validate", "normalize") or (args.command == "render" and not args.skip_validation):
            normalized = client.request("POST", "/api/input/normalize", body=body, content_type=media, auth=False)
            if args.command == "validate":
                emit({"valid": True}, machine)
                return 0
            if args.command == "normalize":
                if args.output:
                    emit(atomic_save(args.output, [(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode()], args.force), machine)
                else:
                    emit(normalized, machine)
                return 0
        status = client.submit(body, media, args.image_format, args.edit, args.name)
        # Show the accepted ID before waiting/downloading, including when interrupted.
        progress(status)
        if args.command == "render":
            status = client.wait(status["id"], args.wait_timeout, args.interval, progress)
            if terminal_code(status):
                emit(status, machine)
                return 5
            archive_id = status.get("archive_id") or status["id"]
            directory = Path(args.output) / safe_name(archive_id)
            names = [safe_name(item["name"]) for item in status["files"]]
            names.append("well_data.yaml")
            # Fail before downloading if any existing file would be overwritten.
            if not args.force and any((directory / name).exists() for name in names):
                raise ClientError(f"输出目录已有产物：{directory}；选择新目录或 --force", 2)
            downloads = [client.download(archive_id, name, directory / name, args.force) for name in dict.fromkeys(names)]
            emit({"job": status, "archive_id": archive_id, "downloads": downloads}, machine)
        else:
            emit(status, machine)
    elif args.command == "jobs":
        if args.action == "status":
            status = client.status(args.job_id)
        elif args.action == "wait":
            status = client.wait(args.job_id, args.wait_timeout, args.interval, progress)
        else:
            status = None
            for status in client.events(args.job_id, args.wait_timeout):
                emit(status, machine)
            return terminal_code(status or {})
        emit(status, machine)
        return terminal_code(status)
    elif args.command == "download":
        output = args.output or (f"wellbore-{segment(args.archive_id)}.zip" if args.file == "zip" else safe_name(args.file))
        emit(client.download(args.archive_id, args.file, output, args.force), machine)
    return 0


def main(argv=None):
    raw = sys.argv[1:] if argv is None else argv
    machine = "--json" in raw
    args = None
    try:
        args = parser().parse_args(raw)
        return run(args)
    except ClientError as exc:
        problem = exc.problem
        # An upstream diagnostic may echo the credential: redact at the final boundary.
        secrets = [os.environ.get("WELLBORE_API_KEY", "")]
        try:
            _, secret = resolve(getattr(args, "base_url", None), getattr(args, "key_file", None))
            secrets.append(secret)
        except (ClientError, OSError):
            pass
        encoded = json.dumps(problem, ensure_ascii=False)
        for secret in secrets:
            if secret:
                encoded = encoded.replace(secret, "[REDACTED]")
        print(encoded if machine else "错误：" + encoded, file=sys.stderr)
        return exc.code
    except BrokenPipeError:
        return 0
    except (OSError, ValueError) as exc:
        emit_error = {"title": "本机读写或数据错误", "detail": str(exc)}
        print(json.dumps(emit_error, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断客户端；已受理的服务端任务仍可能继续，请用 jobs status 或 history 查询。", file=sys.stderr)
        return 130
