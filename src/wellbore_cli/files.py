"""Bounded inputs and atomic downloads; no interpretation of domain data."""
import os
import sys
import tempfile
from pathlib import Path

from .errors import ClientError

MAX_INPUT_BYTES = 1024 * 1024


def read_input(source, input_format=None):
    suffix = Path(source).suffix.lower() if source != "-" else ""
    fmt = input_format or {".json": "json", ".yaml": "yaml", ".yml": "yaml"}.get(suffix)
    if not fmt:
        raise ClientError("输入须为 .yaml/.yml/.json；标准输入请指定 --input-format", 2)
    if source == "-":
        body = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(source).open("rb") as handle:
            body = handle.read(MAX_INPUT_BYTES + 1)
    if not body or len(body) > MAX_INPUT_BYTES:
        raise ClientError("输入不能为空，且不得超过 1 MiB", 2)
    return body, "application/" + fmt


def safe_name(name):
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if (not name or name.endswith((".", " "))
            or name.split(".")[0].upper() in reserved
            or any(c in name for c in ("/", "\\", "\0", ":"))):
        raise ClientError("产物文件名必须是不含路径分隔符的单个名称", 2)
    return name


def atomic_save(destination, chunks, force=False):
    path = Path(destination).expanduser()
    if os.path.lexists(path) and not force:
        raise ClientError(f"文件已存在：{path}；改用新路径或 --force", 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".wellbore-", dir=path.parent)
    count = 0
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in chunks:
                out.write(chunk)
                count += len(chunk)
            out.flush()
            os.fsync(out.fileno())
        if force:
            os.replace(temp, path)
        else:
            # Exclusive publication also protects against concurrent writers.
            try:
                os.link(temp, path)
            except FileExistsError:
                raise ClientError(f"文件已存在：{path}；改用新路径或 --force", 2) from None
            except OSError:
                # FAT/exFAT and some SMB shares have no hard links. Reserve the
                # destination exclusively, then atomically replace the reservation.
                if os.path.lexists(path):
                    raise ClientError(f"文件已存在：{path}；改用新路径或 --force", 2) from None
                try:
                    reserved = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    raise ClientError(f"文件已存在：{path}；改用新路径或 --force", 2) from None
                try:
                    os.close(reserved)
                    os.replace(temp, path)
                except OSError:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                    raise
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"警告：临时文件未能删除：{temp}（{exc}）", file=sys.stderr)
    return {"path": str(path.resolve()), "bytes": count}
