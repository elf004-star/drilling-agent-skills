"""Configuration resolution; credentials never appear in public settings."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .errors import ClientError

DEFAULT_URL = "https://ccqwell.vip.cpolar.cn"


def config_dir():
    return Path(os.environ.get("WELLBORE_CONFIG_DIR") or
                Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "wellbore")


def load():
    path = config_dir() / "config.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value
    except (ValueError, OSError) as exc:
        raise ClientError("配置文件不可读或不是 JSON 对象") from exc


def validate_url(url):
    p = urlsplit(url)
    if p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise ClientError("基地址只能包含协议、主机和端口，不得包含凭据、路径或参数", 2)
    if not p.hostname or p.scheme not in ("https", "http"):
        raise ClientError("基地址必须是有效的 HTTPS URL", 2)
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ClientError("远程服务必须使用 HTTPS；HTTP 仅允许本机开发", 2)
    try:
        _ = p.port
    except ValueError as exc:
        raise ClientError("基地址端口无效", 2) from exc
    return url.rstrip("/")


def resolve(url=None, key_file=None):
    settings = load()
    base = validate_url(url or os.environ.get("WELLBORE_BASE_URL") or
                        settings.get("base_url") or DEFAULT_URL)
    secret_path = Path(key_file).expanduser() if key_file else config_dir() / "api-key"
    key = None if key_file else os.environ.get("WELLBORE_API_KEY")
    if key is None and secret_path.exists():
        key = secret_path.read_text(encoding="utf-8").strip()
    if key_file and not secret_path.is_file():
        raise ClientError("指定的密钥文件不存在", 2)
    key = (key or "").strip()
    if "\n" in key or "\r" in key:
        raise ClientError("密钥必须是一行", 2)
    return base, key


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        if os.name != "nt":
            os.fchmod(out.fileno(), 0o600)
        out.write(data)
