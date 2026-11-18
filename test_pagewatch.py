# -*- coding: utf-8 -*-
"""pagewatch 端到端测试: 起本地服务, 走完 add/check/变更/边界 全链路"""
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import http.server
from pathlib import Path

ROOT = Path(__file__).parent
PY = sys.executable
TMP = Path(tempfile.mkdtemp(prefix="pw_test_"))
ENV = {**os.environ, "PAGEWATCH_HOME": str(TMP)}


def run(*args):
    r = subprocess.run([PY, str(ROOT / "pagewatch.py"), *args],
                       capture_output=True, text=True, env=ENV, cwd=ROOT)
    print((r.stdout + r.stderr).strip())
    print()


class Handler(http.server.BaseHTTPRequestHandler):
    content = b"<html><body><h1>price: 599</h1></body></html>"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(Handler.content)

    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(("127.0.0.1", 8765), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

try:
    print("=== 1. add 监控项 ===")
    run("add", "http://127.0.0.1:8765/", "--selector", "h1", "--name", "probe")

    print("=== 2. 首次检查(建基线) ===")
    run("check")

    print("=== 3. 页面变化 -> 应触发通知 ===")
    Handler.content = b"<html><body><h1>price: 499</h1></body></html>"
    run("check")

    print("=== 4. 边界: 间隔格式非法 ===")
    run("add", "http://127.0.0.1:8765/", "--interval", "30x")

    print("=== 5. 边界: selector 匹配不到(空内容hash) ===")
    run("add", "http://127.0.0.1:8765/", "--selector", ".nope", "--name", "nope", "--force")
    run("check")

    srv.shutdown()
    print("=== 6. 边界: 服务挂掉(抓取失败不崩溃) ===")
    run("check", "--dry-run")
finally:
    srv.server_close()
    shutil.rmtree(TMP, ignore_errors=True)

print("ALL DONE")
