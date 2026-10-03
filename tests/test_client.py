import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import IncompleteRead
from unittest.mock import patch

from wellbore_cli.cli import main, parser
from wellbore_cli.client import Client
from wellbore_cli.config import private_write, resolve, validate_url
from wellbore_cli.errors import ClientError
from wellbore_cli.files import atomic_save, read_input, safe_name


class Handler(BaseHTTPRequestHandler):
    requests = []
    state = "success"
    artifact = b"a real downloaded artifact"

    def log_message(self, *args):
        pass

    def reply(self, value, code=200, media="application/json"):
        data = json.dumps(value).encode() if media.endswith("json") else value
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def snapshot(self):
        return {"id": "job-1", "archive_id": "archive-1", "status": self.state,
                "warnings": [{"step": "绘图", "message": "降级"}],
                "files": [{"name": "plot.svg", "bytes": len(self.artifact)}],
                "error": {"detail": "bad input", "traceId": "trace-test"} if self.state == "failed" else None}

    def record(self, body=None):
        self.requests.append((self.command, self.path, dict(self.headers), body))

    def do_GET(self):
        self.record()
        if self.path == "/api/health":
            self.reply({"status": "ok"})
        elif self.path == "/api/jobs/job-1/events":
            payload = b": comment\n\nevent: status\ndata: " + json.dumps(self.snapshot()).encode() + b"\n\n"
            self.reply(payload, media="text/event-stream")
        elif self.path.startswith("/api/jobs/"):
            self.reply(self.snapshot())
        elif self.path.startswith("/api/renders/archive-1/"):
            self.reply(self.artifact, media="image/svg+xml")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/leak")
            self.end_headers()
        else:
            self.reply({"title": "无权限", "detail": "missing credential", "traceId": "t", "status": 401}, 401)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.record(body)
        if self.path == "/api/input/normalize":
            if body == b"bad":
                self.reply({"title": "校验失败", "detail": "field error", "errors": [{"path": "wellInfo", "line": 1}], "traceId": "t"}, 422)
            else:
                self.reply({"wellInfo": None, "stratigraphy": []})
        else:
            self.reply(self.snapshot(), 202)


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        Handler.requests.clear()
        Handler.state = "success"
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"WELLBORE_CONFIG_DIR": str(self.root / "config"), "WELLBORE_API_KEY": "test-secret", "WELLBORE_BASE_URL": self.url})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = Client(self.url, "test-secret", no_proxy=True)

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*args, "--no-proxy"])
        return code, out.getvalue(), err.getvalue()

    def test_raw_input_auth_and_edit_mapping(self):
        body = "地层: 测试".encode()
        result = self.client.submit(body, "application/yaml", "svg", "old", "井名")
        _, path, headers, received = Handler.requests[-1]
        self.assertIn("edit=old", path)
        self.assertIn("image_format=svg", path)
        self.assertEqual(headers["Authorization"], "Bearer test-secret")
        self.assertEqual(headers["Content-Type"], "application/yaml")
        self.assertEqual(received, body)
        self.assertEqual(result["archive_id"], "archive-1")

    def test_public_health_and_validation_never_send_key(self):
        source = self.root / "input.yaml"
        source.write_text("stratigraphy: {}")
        for args in (["health", "--json"], ["validate", str(source), "--json"]):
            code, out, _ = self.invoke(args)
            self.assertEqual(code, 0)
            json.loads(out)
            self.assertNotIn("Authorization", Handler.requests[-1][2])
        self.assertFalse(any(path.startswith("/api/jobs") for _, path, _, _ in Handler.requests))

    def test_preflight_stops_before_submission(self):
        source = self.root / "bad.yaml"
        source.write_text("bad")
        code, out, err = self.invoke(["render", str(source), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err)["errors"][0]["path"], "wellInfo")
        self.assertEqual(len(Handler.requests), 1)

    def test_render_uses_archive_id_and_downloads_normalized_input(self):
        source = self.root / "input.yaml"
        source.write_text("stratigraphy: {}")
        code, out, err = self.invoke(["render", str(source), "-o", str(self.root / "output"), "--json"])
        self.assertEqual(code, 0, err)
        value = json.loads(out)
        self.assertEqual(value["archive_id"], "archive-1")
        self.assertEqual(len(value["downloads"]), 2)
        self.assertTrue((self.root / "output/archive-1/plot.svg").exists())
        self.assertTrue((self.root / "output/archive-1/well_data.yaml").exists())
        self.assertEqual(value["job"]["warnings"][0]["message"], "降级")
        self.assertEqual(sum(method == "POST" and path.startswith("/api/jobs") for method, path, _, _ in Handler.requests), 1)

    def test_failed_job_http_200_is_exit_five_and_no_download(self):
        Handler.state = "failed"
        code, out, _ = self.invoke(["jobs", "wait", "job-1", "--json"])
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)["error"]["traceId"], "trace-test")
        self.assertFalse(any("renders" in path for _, path, _, _ in Handler.requests))

    def test_sse_terminal_once(self):
        code, out, _ = self.invoke(["jobs", "events", "job-1", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(json.loads(out)["status"], "success")

    def test_timeout_has_no_resubmission(self):
        Handler.state = "running"
        with self.assertRaises(ClientError) as ctx:
            self.client.wait("job-1", wait_timeout=0.03, interval=0.02)
        self.assertEqual(ctx.exception.code, 4)
        self.assertTrue(all(method == "GET" for method, _, _, _ in Handler.requests))

    def test_http_problem_preserved(self):
        with self.assertRaises(ClientError) as ctx:
            self.client.request("GET", "/denied")
        self.assertEqual(ctx.exception.code, 3)
        self.assertEqual(ctx.exception.problem["traceId"], "t")

    def test_redirect_is_not_followed(self):
        with self.assertRaisesRegex(ClientError, "重定向"):
            self.client.request("GET", "/redirect")
        self.assertEqual(len(Handler.requests), 1)

    def test_global_options_at_all_levels(self):
        for args in (["--json", "jobs", "status", "job-1"], ["jobs", "--json", "status", "job-1"], ["jobs", "status", "job-1", "--json"]):
            self.assertTrue(parser().parse_args(args).json)

    def test_atomic_download_overwrite_and_partial_failure(self):
        target = self.root / "file"
        target.write_bytes(b"old")
        with self.assertRaises(ClientError):
            self.client.download("archive-1", "plot.svg", target)
        self.assertEqual(target.read_bytes(), b"old")
        self.client.download("archive-1", "plot.svg", target, force=True)
        self.assertEqual(target.read_bytes(), Handler.artifact)
        def broken():
            yield b"partial"
            raise ClientError("interrupted", 4)
        with self.assertRaises(ClientError):
            atomic_save(target, broken(), force=True)
        self.assertEqual(target.read_bytes(), Handler.artifact)
        self.assertEqual(list(self.root.glob(".wellbore-*")), [])

    def test_path_and_input_limits(self):
        for name in ("../secret", "..\\secret", "..", "", "C:secret", ".. ", "CON.txt"):
            with self.assertRaises(ClientError):
                safe_name(name)
        source = self.root / "large.yaml"
        source.write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(ClientError):
            read_input(str(source))
        with self.assertRaises(ClientError):
            read_input("-", None)

    def test_config_precedence_and_private_key_permissions(self):
        path = self.root / "key"
        private_write(path, "file-secret\n")
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(resolve(key_file=path)[1], "file-secret")
        self.assertEqual(resolve()[1], "test-secret")
        self.assertEqual(resolve("https://override.example")[0], "https://override.example")
        for url in ("http://remote.example", "https://user:pass@example.com", "https://example.com/path", "https://example.com?key=x"):
            with self.assertRaises(ClientError):
                validate_url(url)

    def test_skill_install_and_template_offline(self):
        code, out, err = self.invoke(["skill", "install", "--dir", str(self.root / "skills"), "--json"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "skills/wellbore/SKILL.md").exists())
        self.assertTrue((self.root / "skills/wellbore/assets/straight.yaml").exists())
        code, _, _ = self.invoke(["skill", "install", "--dir", str(self.root / "skills"), "--json"])
        self.assertEqual(code, 2)
        code, out, _ = self.invoke(["template", "straight", "--json"])
        self.assertEqual(code, 0)
        self.assertIn("wellInfo", json.loads(out)["yaml"])
        self.assertEqual(Handler.requests, [])

    def test_uncertain_submit_never_retries(self):
        from urllib.error import URLError
        with patch.object(self.client.opener, "open", side_effect=URLError("disconnect")) as opening:
            with self.assertRaisesRegex(ClientError, "提交结果未知") as ctx:
                self.client.submit(b"input", "application/yaml")
            self.assertEqual(ctx.exception.code, 4)
            opening.assert_called_once()

    def test_interrupted_response_keeps_uncertain_submit_diagnostic(self):
        response = contextlib.nullcontext(io.BytesIO(b"not-json"))
        with patch.object(self.client, "open", return_value=response):
            with self.assertRaisesRegex(ClientError, "提交结果未知"):
                self.client.submit(b"input", "application/yaml")

    def test_explicit_key_file_redaction(self):
        path = self.root / "key"
        path.write_text("explicit-secret")
        error = ClientError("oops", problem={"detail": "echo explicit-secret"})
        with patch("wellbore_cli.cli.Client.request", side_effect=error):
            code, _, err = self.invoke(["account", "--key-file", str(path), "--json"])
        self.assertEqual(code, 1)
        self.assertNotIn("explicit-secret", err)
        self.assertIn("REDACTED", err)

    def test_sse_transport_failure_code(self):
        with patch.object(self.client, "_events", side_effect=IncompleteRead(b"partial")):
            with self.assertRaises(ClientError) as ctx:
                list(self.client.events("job-1"))
        self.assertEqual(ctx.exception.code, 4)


if __name__ == "__main__":
    unittest.main()
