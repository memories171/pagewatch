#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""京东商品价格数据源插件 (丢到 PAGEWATCH_HOME/plugins/sources/jd_price.py 即可)

用法:
  pagewatch add https://item.jd.com/100012043978.html --source jd_price --compare num --name 京东显卡

原理: 京东移动端商品页的 HTML 里内嵌了 priceFloor JSON 价格数据,
直接正则提取, 不依赖已失效的 p.3.cn 接口。

注意:
  京东对未登录用户隐藏真实价格 (显示成 1??9), 本插件会明确报错而不是给假数据。
  想看真实价格: 浏览器登录京东 -> F12 复制 Cookie -> set JD_COOKIE=pt_key=xxx;pt_pin=xxx;
  Cookie 会过期, 失效后再重新复制即可。
"""

import os
import re

import requests

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"


def fetch(entry) -> str:
    """entry 为监控项 dict, 返回文本 (建议配合 --compare num 只盯数字)"""
    m = re.search(r"(\d{6,})", entry["url"])
    if not m:
        raise ValueError(f"jd_price 数据源需要京东商品链接 (其中含 SKU 数字): {entry['url']}")
    sku = m.group(1)

    headers = {"User-Agent": UA}
    cookie = os.environ.get("JD_COOKIE")
    if cookie:
        headers["Cookie"] = cookie

    r = requests.get(f"https://item.m.jd.com/product/{sku}.html",
                     headers=headers, timeout=15)
    r.raise_for_status()

    m2 = re.search(r'"priceFloor":\s*\{[^}]*?"price":"([^"]*)"', r.text)
    if not m2:
        raise ValueError("商品页里没找到价格字段, 京东页面结构可能又变了, 需要更新插件")
    price = m2.group(1)

    if "?" in price:
        raise ValueError("京东未登录隐藏了价格 (如 '1??9'); "
                         "请在环境变量 JD_COOKIE 配置已登录 Cookie 后重试")
    return f"京东价 {price}"
