# 省考每日打卡卡 · 云端推送

每天北京时间 09:10 由 GitHub Actions 在云端生成打卡卡并通过 Bark 推送到 iPhone 通知栏，**完全不依赖本地电脑开关机**。

## 内容结构

1. 今日时政要点（自动抓取新闻源，按公考相关度排序）
2. 今日 8 项碎片打卡任务清单
3. 每日小练习（按星期轮换：周一成语辨析、周二类比推理、周三数字推理、周四常识判断、周五定义判断、周六资料分析、周日综合小测），4 套题目按周数循环
4. 申论素材 1 条（28 条按日期轮换）
5. 答案与解析（文末，先做题再看）

## 接入步骤

1. **iPhone 安装 Bark**：App Store 搜索"Bark"免费安装，打开后复制首页显示的推送密钥（形如 `https://api.day.app/xxxxxxx/`，其中 `xxxxxxx` 就是密钥）
2. **登录 GitHub**：浏览器打开 github.com 登录（登录遇到问题可换网络环境或重新注册账号）
3. **创建私有仓库**：GitHub 网页右上角 + → New repository → 名称如 `gdexam-daily-push` → 勾选 **Private** → Create
4. **上传本仓库所有文件**（保持目录结构，`.github/workflows/daily-push.yml` 必须在正确路径）：网页端 Add file → Upload files 逐目录上传，或本地 git push
5. **配置密钥**：仓库 Settings → Secrets and variables → Actions → New repository secret，添加 `BARK_DEVICE_KEY`，值为第 1 步的密钥（`BARK_SERVER` 可选，自建 Bark 服务器时才需要）
6. **启用 Actions**：仓库 Actions 页确认工作流"每日打卡卡推送"存在；在 Actions → 每日打卡卡推送 → Run workflow 手动触发一次，验证手机能否收到推送
7. 完成：此后每天 09:10 左右手机通知栏自动收到打卡卡（GitHub 定时任务可能有几分钟延迟）

## 本地测试（可选）

```bash
python scripts/push.py --dry-run   # 仅打印打卡卡内容，不推送
```

## 目录结构

```
├── .github/workflows/daily-push.yml   # 云端定时任务
├── scripts/push.py                    # 推送脚本（纯标准库）
└── data/
    ├── mon~sun.json                   # 7个星期 × 4套练习题
    └── shenlun.json                   # 28条申论素材
```
