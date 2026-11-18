#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟一个价格会变化的商品页, 供本地体验 pagewatch

用法: python examples/demo_server.py
然后另开终端: pagewatch add http://127.0.0.1:8899/product.html --selector .price --interval 10s --name demo
"""

import http.server
import itertools
import threading
import time

PRICES = itertools.cycle(["¥599", "¥549", "¥499", "¥699"])
state = {"price": "¥599", "time": time.strftime("%H:%M:%S")}


def ticker():
    """每 8 秒换一次价格, 模拟商家调价"""
    for p in PRICES:
        state["price"] = p
        state["time"] = time.strftime("%H:%M:%S")
        time.sleep(8)


PAGE = """<html><body>
<h1>显卡 GTX 5090Ti (演示页)</h1>
<div class="price">{price}</div>
<p>页面每 8 秒变一次价格, 当前更新时间: {time}</p>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.format(**state).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=ticker, daemon=True).start()
    print("演示页已启动: http://127.0.0.1:8899/product.html  (Ctrl+C 停止)")
    http.server.HTTPServer(("127.0.0.1", 8899), Handler).serve_forever()
