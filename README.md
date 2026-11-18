# pagewatch

> 轻量级网页变更监控器 —— 盯网页这件事交给程序，你只收结果。

监控任意网页的指定部分（CSS 选择器），内容变化时第一时间推送通知：
商品降价、考位放名额、教务处公告、开源项目发版……只要页面上有，就能盯。

<!-- TODO: 发布前在这里放一张 10 秒 demo GIF（asciinema 录制转 GIF，或 ScreenToGif） -->

## 用户故事

我盯着一个 599 的显卡两个月了，配置一行：

```bash
pagewatch add "https://example.com/gpu" --selector ".price" --interval 30m --name gpu
pagewatch daemon
```

三天后微信弹出通知：**[pagewatch] gpu 有变化**。下单，收工。

再比如：盯学校教务处的通知页（没有 RSS、没有公众号推送的那种），
盯某开源项目的 Release 页，盯机票价格——它把「怕错过」这件事自动化了。

## 特性

- **轻**：单文件核心（约 300 行），依赖只有 `requests` + `beautifulsoup4`，无数据库、无 Docker、无 Web 界面
- **精准**：CSS 选择器只盯页面局部，忽略广告和无关改版
- **抗误报**：4 种对比策略（全文/归一化/仅数字/正则），时间戳抖动、文案变化都能过滤
- **通知**：Server酱（微信）/ 通用 Webhook 内置；**插件目录**让你 20 行代码接入任意渠道
- **可追溯**：每个监控项保留最近 20 次变更历史

## 安装

```bash
# 发布 PyPI 后
pip install pagewatch

# 或从源码安装
git clone https://github.com/memories171/pagewatch.git
cd pagewatch
pip install -e .
```

要求 Python >= 3.10。

## 快速上手

```bash
# 添加监控: 只盯价格元素, 每 30 分钟检查一次
pagewatch add "https://example.com/gpu" --selector ".price" --interval 30m --name gpu

# 盯价格数值: 页面文案乱变不管, 只有数字变了才算变更
pagewatch add "https://example.com/gpu" --selector ".price" --compare num --name gpu

# 查看监控列表
pagewatch list

# 手动检查一轮
pagewatch check

# 试运行(不落盘、不通知)
pagewatch check --dry-run

# 常驻后台, 按各自间隔自动检查
pagewatch daemon

# 移除
pagewatch remove gpu
```

间隔格式：`30s` / `10m` / `2h` / `1d`。

## 对比策略（解决误报）

| 策略 | 说明 | 适用场景 |
|---|---|---|
| `raw` | 全文对比（默认） | 页面完全静态 |
| `norm` | 去空白去数字后对比 | 公告页带时间戳，日期变了不算变更 |
| `num` | 只提取数字对比 | 盯价格/库存数，文案乱变不管 |
| `regex:模式` | 只提取正则匹配内容对比 | 只盯页面上某一小段 |

```bash
# 例: 只盯"价格xx元"这段内容
pagewatch add <url> --selector ".price" --compare "regex:价格.*?元" --name gpu
```

## 通知配置

| 渠道 | 启用方式 |
|---|---|
| `serverchan` | 配环境变量 `SERVERCHAN_SENDKEY`（[Server酱](https://sct.ftqq.com/)，推送到微信） |
| `webhook` | 配环境变量 `PAGEWATCH_WEBHOOK`，变更时 POST `{"title", "content"}` JSON |
| **自定义插件** | 把含 `send(title, content)` 函数的 `.py` 文件放到 `PAGEWATCH_HOME/plugins/` 下，文件名即渠道名 |

不配任何渠道则打印到终端。`PAGEWATCH_NOTIFY=渠道1,渠道2` 可显式指定发哪些渠道。

**自定义通知插件**（20 行接入 Telegram / 邮件 / 钉钉等任意渠道，无需改核心代码）：

```python
# 文件: ~/.pagewatch/plugins/telegram.py
import os
import requests

def send(title: str, content: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
        json={"chat_id": os.environ["TG_CHAT_ID"], "text": f"{title}\n{content}"},
        timeout=10,
    )
```

保存后立即生效，变更会自动推送到 telegram 渠道；插件报错只记日志，不影响其他渠道。

## 数据存储

所有监控项存为本地 JSON（含基线 hash、历史记录），默认位置 `~/.pagewatch/`。
用 `PAGEWATCH_HOME` 环境变量可指定任意目录：

```bash
export PAGEWATCH_HOME=/path/to/your/dir
```

## 设计原则

- CLI 优先，一件事做到极致：**检测变化 → 通知**
- 无常驻服务依赖，一台电脑 / 一块树莓派都能跑
- 单文件可整体阅读，方便魔改

## Roadmap

- [x] v0.1: add/list/remove/check/daemon + Server酱/Webhook 通知
- [x] v0.2: 对比策略（raw/norm/num/regex）+ 通知渠道插件目录
- [ ] JSON / RSS 数据源（盯 API 返回值）
- [ ] 变更动作钩子（`--on-change` 执行任意命令）
- [ ] GitHub Action 版（push 驱动，无需常驻进程）
- [ ] 变更 diff 高亮输出（只推送改了的那几行）

## 开发

```bash
pip install -e .[dev]
python test_pagewatch.py    # 端到端测试: 本地起服务, 验证变更检测/通知/边界
```

## License

[MIT](LICENSE)
