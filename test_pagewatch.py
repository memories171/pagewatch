# -*- coding: utf-8 -*-
"""pagewatch v0.2 端到端测试: 通知插件目录 + 对比策略 + 原有功能回归"""
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
passed = []
failed = []


def run(*args, env_extra=None):
    env = {**ENV, **(env_extra or {})}
    r = subprocess.run([PY, str(ROOT / "pagewatch.py"), *args],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    print((r.stdout + r.stderr).strip())
    print()
    return r.stdout + r.stderr


def expect(label, out, keyword):
    (passed if keyword in out else failed).append(label)
    print(f"{'✅' if keyword in out else '❌'} {label}  (期望含: {keyword})\n")


class Handler(http.server.BaseHTTPRequestHandler):
    content = b"<html><body><h1>price: 599 in stock</h1></body></html>"

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
    # ---------- 回归: 基础流程 ----------
    print("========== 回归: 基础流程 ==========")
    out = run("add", "http://127.0.0.1:8765/", "--selector", "h1", "--name", "probe")
    expect("add 监控项", out, "已添加")
    out = run("check")
    expect("首次检查建基线", out, "建立基线")
    Handler.content = b"<html><body><h1>price: 499 in stock</h1></body></html>"
    out = run("check")
    expect("变更触发通知(stdout兜底)", out, "⚡内容有变化")

    # ---------- 新功能 1: 对比策略 ----------
    print("========== 对比策略 ==========")
    out = run("add", "http://127.0.0.1:8765/", "--selector", "h1",
              "--compare", "num", "--name", "numcase", "--force")
    expect("add --compare num", out, "compare=num")
    run("check")  # numcase 建基线 (内容: price 499)
    # 数字不变, 文字变 -> num 策略应判无变化
    Handler.content = b"<html><body><h1>price: 499 SOLD OUT</h1></body></html>"
    out = run("check")
    expect("num策略: 数字没变->无变化", out, "numcase  无变化")
    # 数字变了 -> 触发
    Handler.content = b"<html><body><h1>price: 299 SOLD OUT</h1></body></html>"
    out = run("check")
    expect("num策略: 数字变了->触发", out, "numcase  ⚡内容有变化")

    # norm 策略: 先切到公告页再建基线, 之后只改日期
    Handler.content = "<html><body><h1>公告  发布于 2026-11-18</h1></body></html>".encode("utf-8")
    out = run("add", "http://127.0.0.1:8765/", "--selector", "h1",
              "--compare", "norm", "--name", "normcase", "--force")
    run("check")  # normcase 建基线
    Handler.content = "<html><body><h1>公告  发布于 2026-11-19</h1></body></html>".encode("utf-8")
    out = run("check")
    expect("norm策略: 只有日期变->无变化", out, "normcase  无变化")

    out = run("add", "http://x.com", "--compare", "bad", "--name", "x")
    expect("非法策略报错", out, "未知对比策略")

    # ---------- 新功能 2: 通知插件目录 ----------
    print("========== 通知插件 ==========")
    pdir = TMP / "plugins"
    pdir.mkdir()
    (pdir / "beep.py").write_text(
        "import os\n"
        "def send(title, content):\n"
        "    with open(os.path.join(os.environ['PAGEWATCH_HOME'], 'notify.log'), 'a', encoding='utf-8') as f:\n"
        "        f.write(title + '\\n')\n",
        encoding="utf-8")
    Handler.content = b"<html><body><h1>price: 599 in stock</h1></body></html>"
    out = run("add", "http://127.0.0.1:8765/", "--selector", "h1",
              "--name", "plug", "--force")
    run("check")  # plug 建基线
    Handler.content = b"<html><body><h1>price: 199 in stock</h1></body></html>"
    out = run("check", env_extra={"PAGEWATCH_NOTIFY": "beep"})
    expect("插件渠道被调用", out, "通知: beep")
    log = (TMP / "notify.log")
    expect("插件 send() 真正执行(写入日志)", log.read_text(encoding="utf-8") if log.exists() else "", "[pagewatch] plug")

    Handler.content = b"<html><body><h1>price: 99 in stock</h1></body></html>"
    out = run("check", env_extra={"PAGEWATCH_NOTIFY": "nope"})
    expect("不存在的渠道给出提示", out, "未找到渠道")

    # ---------- 新功能 3: 数据源插件 ----------
    print("========== 数据源插件 ==========")
    sdir = TMP / "plugins" / "sources"
    sdir.mkdir(parents=True)
    (sdir / "fake.py").write_text("def fetch(entry):\n    return 'FAKE-CONTENT-42'\n", encoding="utf-8")
    out = run("add", "http://127.0.0.1:8765/", "--source", "fake", "--name", "src1", "--force")
    expect("add --source fake", out, "source=fake")
    out = run("check")
    import hashlib
    want = hashlib.sha256("FAKE-CONTENT-42".encode()).hexdigest()[:12]
    expect("fake数据源真实接管了抓取", out, f"建立基线 ({want})")

    out = run("add", "http://x.com", "--source", "nope", "--name", "bad")
    expect("未安装的数据源给出提示", out, "未安装")

    # ---------- 边界 ----------
    print("========== 边界 ==========")
    srv.shutdown()
    out = run("check", "--dry-run")
    expect("服务挂掉不崩溃", out, "抓取失败")
finally:
    srv.server_close()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"========== 结果: {len(passed)} 通过, {len(failed)} 失败 ==========")
sys.exit(1 if failed else 0)
