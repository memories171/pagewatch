#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pagewatch -- 轻量级网页变更监控器 (单文件核心)

用法:
  pagewatch add <url> [--selector CSS] [--interval 30m] [--name NAME] [--compare 策略]
  pagewatch list
  pagewatch remove <name>
  pagewatch check               # 检查一轮
  pagewatch check --dry-run     # 只看结果, 不落盘/不通知
  pagewatch daemon              # 常驻循环

对比策略 (--compare):
  raw          全文对比 (默认)
  norm         去空白去数字后对比, 忽略时间戳等无关抖动
  num          只提取数字对比, 适合盯价格
  regex:模式   只提取正则匹配内容对比, 如 regex:价格.*?元

通知渠道 (环境变量 PAGEWATCH_NOTIFY=渠道1,渠道2 可选, 缺省自动):
  serverchan   内置, 配 SERVERCHAN_SENDKEY 后自动启用, 推送到微信
  webhook      内置, 配 PAGEWATCH_WEBHOOK 后自动启用, POST JSON
  自定义插件   把含 send(title, content) 函数的 .py 文件放到
               PAGEWATCH_HOME/plugins/ 下, 文件名即渠道名, 立即可用
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STORE = Path(os.environ.get("PAGEWATCH_HOME", Path.home() / ".pagewatch")) / "watchlist.json"
UA = "Mozilla/5.0 (compatible; pagewatch/0.2)"
UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}
BUILTIN_ENV = {"serverchan": "SERVERCHAN_SENDKEY", "webhook": "PAGEWATCH_WEBHOOK"}


# ---------- 存储 ----------

def load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {}


def save(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_interval(s: str) -> float:
    unit, num = s[-1], float(s[:-1])
    if unit not in UNIT:
        raise ValueError(f"间隔格式不对: {s} (支持 30s/10m/2h/1d)")
    return UNIT[unit] * num


# ---------- 抓取 ----------

def fetch_text(url: str, selector: str | None) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    if not selector:
        return r.text.strip()
    nodes = BeautifulSoup(r.text, "html.parser").select(selector)
    return "\n".join(n.get_text(strip=True) for n in nodes if n.get_text(strip=True))


# ---------- 对比策略 ----------

def digest_of(text: str, strategy: str) -> str:
    """按策略归一化后取 12 位 hash"""
    if strategy == "raw":
        norm = text
    elif strategy == "norm":
        norm = re.sub(r"\d+", "", re.sub(r"\s+", " ", text))
    elif strategy == "num":
        norm = " ".join(re.findall(r"\d+(?:\.\d+)?", text))
    elif strategy.startswith("regex:"):
        norm = "|".join(re.findall(strategy.split(":", 1)[1], text))
    else:
        raise ValueError(f"未知对比策略: {strategy} (支持 raw/norm/num/regex:模式)")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


# ---------- 通知 ----------

def _send_serverchan(title: str, content: str) -> None:
    requests.post(f"https://sctapi.ftqq.com/{os.environ['SERVERCHAN_SENDKEY']}.send",
                  data={"title": title, "desp": content}, timeout=10)


def _send_webhook(title: str, content: str) -> None:
    requests.post(os.environ["PAGEWATCH_WEBHOOK"],
                  json={"title": title, "content": content}, timeout=10)


def load_channels() -> dict:
    """内置渠道 + plugins/ 目录下的自定义插件 (文件名即渠道名, 需含 send 函数)"""
    ch = {"serverchan": _send_serverchan, "webhook": _send_webhook}
    pdir = STORE.parent / "plugins"
    if pdir.exists():
        for f in sorted(pdir.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(f.stem, f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if callable(getattr(mod, "send", None)):
                    ch[f.stem] = mod.send
                else:
                    print(f"  [插件] 跳过 {f.name}: 缺少 send(title, content) 函数")
            except Exception as ex:
                print(f"  [插件] 加载失败 {f.name}: {ex}")
    return ch


def notify(title: str, content: str) -> list[str]:
    ch = load_channels()
    sel = os.environ.get("PAGEWATCH_NOTIFY", "").strip()
    if sel:                                   # 显式指定渠道列表
        asked = [n.strip() for n in sel.split(",") if n.strip()]
        names = [n for n in asked if n in ch]
        missing = [n for n in asked if n not in ch]
        if missing:
            print(f"  [通知] 未找到渠道: {','.join(missing)} (可用: {', '.join(ch)})")
    else:                                     # 自动: 内置配了环境变量才发, 插件默认启用
        names = [n for n in ch if n in BUILTIN_ENV and os.environ.get(BUILTIN_ENV[n])]
        names += [n for n in ch if n not in BUILTIN_ENV]

    sent = []
    for n in names:
        try:
            ch[n](title, content)
            sent.append(n)
        except Exception as ex:
            print(f"  [通知] {n} 发送失败: {ex}")
    return sent or ["stdout"]


# ---------- 核心: 检查一轮 ----------

def check_once(dry_run: bool = False) -> None:
    data = load()
    if not data:
        print("watchlist 为空, 先 add 一个监控项")
        return
    now = datetime.now().strftime("%m-%d %H:%M:%S")
    for name, e in data.items():
        try:
            text = fetch_text(e["url"], e.get("selector"))
            digest = digest_of(text, e.get("compare", "raw"))
        except Exception as ex:
            print(f"[{now}] {name}  抓取失败: {ex}")
            continue

        last = e.get("last_hash")
        if last is None:                      # 首次 = 建基线, 不通知
            print(f"[{now}] {name}  建立基线 ({digest})")
        elif last != digest:                  # 变了: 通知 + 记历史
            title = f"[pagewatch] {name} 有变化"
            desc = f"检测时间: {now}\nURL: {e['url']}\n\n--- 新内容 ---\n{text[:800]}"
            channels = ["(dry-run)"] if dry_run else notify(title, desc)
            print(f"[{now}] {name}  ⚡内容有变化 {last} -> {digest}, 通知: {','.join(channels)}")
            if not dry_run:
                e["history"] = (e.get("history") or [])[-19:] + \
                    [{"time": now, "old": last, "new": digest}]
        else:
            print(f"[{now}] {name}  无变化 ({digest})")

        e["last_hash"] = digest
        e["last_content"] = text[:2000]
        e["last_check"] = now
    if not dry_run:
        save(data)


# ---------- 常驻循环 ----------

def daemon() -> None:
    data = load()
    if not data:
        print("watchlist 为空, 先 add 一个监控项")
        return
    print(f"daemon 启动, 共 {len(data)} 个监控项, Ctrl+C 退出")
    next_run = {n: 0.0 for n in data}         # 启动即先跑一轮
    while True:
        now_ts = time.time()
        due = [n for n, t in next_run.items() if t <= now_ts]
        if due:
            check_once()
            for n in due:                     # check_once 已刷新内容, 重新读 interval
                next_run[n] = time.time() + load().get(n, {}).get("interval_sec", 1800)
        time.sleep(min(5, max(1, min(next_run.values()) - time.time())))


# ---------- 命令 ----------

def cmd_add(args) -> None:
    data = load()
    name = args.name or args.url.split("//")[-1].split("/")[0] or "watch"
    if name in data and not args.force:
        sys.exit(f"{name} 已存在, 换个 --name 或加 --force 覆盖")
    digest_of("validate", args.compare)       # 提前校验策略写法, 报错更早更直观
    data[name] = {
        "url": args.url,
        "selector": args.selector,
        "interval_sec": parse_interval(args.interval),
        "compare": args.compare,
        "last_hash": None,
        "history": [],
    }
    save(data)
    print(f"已添加: {name} -> {args.url} (selector={args.selector}, "
          f"interval={args.interval}, compare={args.compare})")


def cmd_list() -> None:
    data = load()
    if not data:
        print("watchlist 为空")
        return
    for name, e in data.items():
        last = e.get("last_check") or "从未检查"
        print(f"- {name}  {e['url']}  interval={e['interval_sec']}s  "
              f"compare={e.get('compare', 'raw')}  上次检查: {last}")


def cmd_remove(name: str) -> None:
    data = load()
    if name not in data:
        sys.exit(f"{name} 不存在")
    data.pop(name)
    save(data)
    print(f"已移除: {name}")


def main() -> None:
    p = argparse.ArgumentParser(description="轻量级网页变更监控器")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("url")
    a.add_argument("--selector", default=None, help="CSS 选择器, 只监控该元素")
    a.add_argument("--interval", default="30m", help="检查间隔, 如 30s/10m/2h/1d")
    a.add_argument("--compare", default="raw", help="对比策略: raw/norm/num/regex:模式")
    a.add_argument("--name", default=None)
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=lambda x: cmd_add(x))

    sub.add_parser("list").set_defaults(fn=lambda x: cmd_list())

    r = sub.add_parser("remove")
    r.add_argument("name")
    r.set_defaults(fn=lambda x: cmd_remove(x.name))

    c = sub.add_parser("check")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(fn=lambda x: check_once(x.dry_run))

    sub.add_parser("daemon").set_defaults(fn=lambda x: daemon())

    args = p.parse_args()
    try:
        args.fn(args)
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
