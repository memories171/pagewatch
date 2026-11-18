#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pagewatch -- 轻量级网页变更监控器 (单文件核心)

用法:
  python pagewatch.py add <url> [--selector CSS] [--interval 30m] [--name NAME]
  python pagewatch.py list
  python pagewatch.py remove <name>
  python pagewatch.py check               # 检查一轮
  python pagewatch.py check --dry-run     # 只看结果, 不落盘/不通知
  python pagewatch.py daemon              # 常驻循环

通知 (环境变量, 可选):
  SERVERCHAN_SENDKEY   Server酱 SendKey, 推送到微信
  PAGEWATCH_WEBHOOK    通用 Webhook, POST JSON {"title", "content"}
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

STORE = Path(os.environ.get("PAGEWATCH_HOME", Path.home() / ".pagewatch")) / "watchlist.json"
UA = "Mozilla/5.0 (compatible; pagewatch/0.1)"
UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


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


# ---------- 通知 ----------

def notify(title: str, content: str) -> list[str]:
    sent = []
    key = os.environ.get("SERVERCHAN_SENDKEY")
    if key:
        requests.post(f"https://sctapi.ftqq.com/{key}.send",
                      data={"title": title, "desp": content}, timeout=10)
        sent.append("serverchan")
    hook = os.environ.get("PAGEWATCH_WEBHOOK")
    if hook:
        requests.post(hook, json={"title": title, "content": content}, timeout=10)
        sent.append("webhook")
    if not sent:
        sent.append("stdout")
    return sent


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
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
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
    data[name] = {
        "url": args.url,
        "selector": args.selector,
        "interval_sec": parse_interval(args.interval),
        "last_hash": None,
        "history": [],
    }
    save(data)
    print(f"已添加: {name} -> {args.url} (selector={args.selector}, interval={args.interval})")


def cmd_list() -> None:
    data = load()
    if not data:
        print("watchlist 为空")
        return
    for name, e in data.items():
        last = e.get("last_check") or "从未检查"
        print(f"- {name}  {e['url']}  interval={e['interval_sec']}s  上次检查: {last}")


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
