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

- **轻**：单文件核心（约 200 行），依赖只有 `requests` + `beautifulsoup4`，无数据库、无 Docker、无 Web 界面
- **精准**：CSS 选择器只盯页面局部，忽略广告和无关改版
- **通知**：Server酱（微信）/ 通用 Webhook，环境变量配置；不配也能跑，结果打印到终端
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

## 通知配置

| 环境变量 | 说明 |
|---|---|
| `SERVERCHAN_SENDKEY` | [Server酱](https://sct.ftqq.com/) SendKey，推送到微信 |
| `PAGEWATCH_WEBHOOK` | 通用 Webhook URL，变更时 POST `{"title", "content"}` JSON |

两者都配则都发；都不配则只打印到终端。示例：

```bash
export SERVERCHAN_SENDKEY=SCTxxxx
export PAGEWATCH_WEBHOOK=https://your.api/hook
pagewatch daemon
```

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
- [ ] 邮件 / Telegram 通知渠道
- [ ] GitHub Action 版（push 驱动，无需常驻进程）
- [ ] 变更 diff 高亮输出（只推送改了的那几行）
- [ ] 数字提取模式（只盯价格数值，忽略页面其他文字变动）

## 开发

```bash
pip install -e .[dev]
python test_pagewatch.py    # 端到端测试: 本地起服务, 验证变更检测/通知/边界
```

## License

[MIT](LICENSE)
