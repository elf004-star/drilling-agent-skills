"""REST transport; writes are never implicitly retried."""
import json
from http.client import HTTPException
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .errors import ClientError
from .files import atomic_save, safe_name

TERMINAL = {"success", "failed", "cancelled"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClientError("服务返回重定向；请确认 --base-url，客户端不会转发密钥")


def segment(value):
    if not value or value in (".", "..") or any(c in value for c in ("/", "\\", "\0")):
        raise ClientError("资源 ID 必须是单个非空路径段", 2)
    return quote(value, safe="")


class Client:
    def __init__(self, base_url, key="", timeout=30, no_proxy=False):
        self.base_url = base_url
        self.key = key
        self.timeout = timeout
        handlers = [NoRedirect()]
        if no_proxy:
            handlers.append(ProxyHandler({}))
        self.opener = build_opener(*handlers)

    def open(self, method, path, body=None, content_type=None, auth=True, params=None, timeout=None):
        if auth and not self.key:
            raise ClientError("请设置 WELLBORE_API_KEY，或运行 wellbore auth set", 3)
        headers = {"Accept": "application/json", "User-Agent": "wellbore-cli/0.1.0"}
        if auth:
            headers["Authorization"] = "Bearer " + self.key
        if content_type:
            headers["Content-Type"] = content_type
        url = self.base_url + path + ("?" + urlencode(params) if params else "")
        request = Request(url, data=body, headers=headers, method=method)
        try:
            return self.opener.open(request, timeout=timeout or self.timeout)
        except HTTPError as exc:
            try:
                problem = json.loads(exc.read())
                if not isinstance(problem, dict):
                    raise ValueError()
            except ValueError:
                problem = {"title": "HTTP 错误", "status": exc.code,
                           "detail": "服务未返回 problem+json；检查服务地址或反向代理"}
            raise ClientError(problem.get("detail", problem.get("title", "HTTP 错误")),
                              3 if exc.code in (401, 403) else 1, problem) from None
        except (URLError, TimeoutError, socket.timeout, OSError, HTTPException) as exc:
            detail = "网络连接失败；检查服务地址、网络和代理设置"
            if method == "POST" and path == "/api/jobs":
                detail += "。提交结果未知，请先查 history，勿自动重新提交（可能重复扣额度）"
            raise ClientError(detail, 4) from exc

    def request(self, method, path, **kwargs):
        with self.open(method, path, **kwargs) as response:
            try:
                return json.load(response)
            except ValueError as exc:
                detail = "服务响应不是有效 JSON；检查服务地址或反向代理"
                if method == "POST" and path == "/api/jobs":
                    detail += "。提交结果未知，请先查 history，勿自动重新提交"
                raise ClientError(detail, 4) from exc
            except (OSError, TimeoutError, HTTPException) as exc:
                detail = "读取响应中断"
                if method == "POST" and path == "/api/jobs":
                    detail += "；提交结果未知，请先查 history，勿自动重新提交"
                raise ClientError(detail, 4) from exc

    def status(self, job_id, timeout=None):
        return self.request("GET", "/api/jobs/" + segment(job_id), timeout=timeout)

    def submit(self, body, content_type, image_format="png", edit=None, name=None):
        params = {"image_format": image_format}
        if edit:
            params["edit"] = edit
        if name is not None:
            params["project_name"] = name
        return self.request("POST", "/api/jobs", body=body, content_type=content_type, params=params)

    def wait(self, job_id, wait_timeout=180, interval=1, progress=None):
        deadline = time.monotonic() + wait_timeout
        previous = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClientError(f"等待超时；任务仍可继续运行，用 jobs wait {job_id} 恢复", 4)
            status = self.status(job_id, timeout=min(self.timeout, remaining))
            state = status.get("status")
            if state not in TERMINAL | {"queued", "running"}:
                raise ClientError("服务返回未知任务状态", 4)
            if progress and previous != state:
                progress(status)
            previous = state
            if state in TERMINAL:
                return status
            time.sleep(min(interval, max(0, deadline - time.monotonic())))

    def events(self, job_id, wait_timeout=180):
        try:
            yield from self._events(job_id, wait_timeout)
        except (OSError, HTTPException, UnicodeError) as exc:
            raise ClientError(f"事件流连接中断；用 jobs wait {job_id} 恢复", 4) from exc

    def _events(self, job_id, wait_timeout):
        # A disconnected feed must not silently create a new rendering task.
        deadline = time.monotonic() + wait_timeout
        with self.open("GET", "/api/jobs/" + segment(job_id) + "/events",
                       timeout=min(self.timeout, wait_timeout)) as response:
            data = []
            event = ""
            for raw in response:
                if time.monotonic() >= deadline:
                    raise ClientError(f"事件流等待超时；用 jobs wait {job_id} 恢复", 4)
                line = raw.decode("utf-8").rstrip("\r\n")
                if not line:
                    if event == "status" and data:
                        try:
                            value = json.loads("\n".join(data))
                        except ValueError as exc:
                            raise ClientError("事件流包含无效 JSON", 4) from exc
                        yield value
                        if value.get("status") in TERMINAL:
                            return
                    data, event = [], ""
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].lstrip(" "))
        raise ClientError(f"事件流提前关闭；用 jobs wait {job_id} 查询", 4)

    def download(self, archive_id, name, destination, force=False):
        suffix = ".zip" if name == "zip" else "/" + quote(safe_name(name), safe="")
        path = "/api/renders/" + segment(archive_id) + suffix
        with self.open("GET", path) as response:
            length = response.headers.get("Content-Length")

            def chunks():
                total = 0
                try:
                    while chunk := response.read(65536):
                        total += len(chunk)
                        yield chunk
                except (OSError, HTTPException) as exc:
                    raise ClientError("下载中断；已保留旧文件，请重新 download", 4) from exc
                if length is not None and total != int(length):
                    raise ClientError("下载未完成；已保留旧文件，请重新 download", 4)

            return atomic_save(destination, chunks(), force)
