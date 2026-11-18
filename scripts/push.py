# -*- coding: utf-8 -*-
"""省考每日打卡卡云端推送脚本（仅使用 Python 标准库，GitHub Actions 无需安装依赖）。

流程：抓取当日新闻 -> 按星期从题库轮换小练习 -> 组装打卡卡 -> 通过 Bark 推送到 iPhone。
配置项全部走环境变量（GitHub Secrets / 本地 export）：
  BARK_DEVICE_KEY  Bark 推送密钥（必填，从 Bark App 首页复制）
  BARK_SERVER      Bark 服务器，默认 https://api.day.app
运行模式：python push.py          正常推送
          python push.py --dry-run 仅打印内容不推送（本地测试用）
"""
import json
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# 北京时间（GitHub 服务器是 UTC，必须换算成东八区再取日期和星期）
CST = timezone(timedelta(hours=8))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
WEEKDAY_FILES = {0: "mon.json", 1: "tue.json", 2: "wed.json", 3: "thu.json", 4: "fri.json", 5: "sat.json", 6: "sun.json"}
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
NEWS_APIS = ["https://60s.viki.moe/v2/60s", "https://60s-cf.viki.moe/v2/60s"]
# 与公考相关度较高的关键词，用于从新闻列表中挑选优先条目
KEYWORDS = ["经济", "改革", "政策", "广东", "深圳", "广州", "大湾区", "发展", "建设", "科技",
            "数据", "增长", "会晤", "国家", "人工智能", "就业", "民生", "乡村", "教育",
            "医疗", "外贸", "进出口", "房价", "金融", "生态", "治理"]
# 每个星期对应的小练习标题
EXERCISE_LABELS = {0: "成语辨析5题", 1: "类比推理5题", 2: "数字推理3题", 3: "常识判断5题",
                   4: "定义判断3题", 5: "资料分析2小题", 6: "综合小测5题"}
TASKS = [
    "时政/常识音频 15分钟",
    "常识刷题 10-20题",
    "成语实词积累 10个",
    "类比推理 10题",
    "数字推理 5-10题",
    "资料分析速算口诀 5分钟",
    "申论素材摘抄 1条",
    "错题回顾 3-5道",
]


def fetch_news():
    """抓取当日新闻要点，多个源依次兜底。"""
    for api in NEWS_APIS:
        try:
            req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            news = data.get("data", {}).get("news", [])
            if news:
                return news
        except Exception:
            continue
    return []


def pick_news(news, n=5):
    """按公考相关度关键词打分排序，取前 n 条。"""
    scored = [(sum(1 for k in KEYWORDS if k in item), i, item) for i, item in enumerate(news)]
    scored.sort(key=lambda x: (-x[0], x[1]))  # 分数降序，同分保持原顺序
    return [item for _, _, item in scored[:n]]


def shuffle_options(s, now):
    """随机打乱选项并重算答案字母（以日期为随机种子，当天保持稳定）。
    题库中正确选项固定在 A 位，不打乱会失去练习意义。"""
    random.seed(now.strftime("%Y%m%d"))
    for q in s["questions"]:
        correct = q["options"][ord(q["answer"]) - 65]
        opts = q["options"][:]
        random.shuffle(opts)
        q["options"] = opts
        q["answer"] = chr(65 + opts.index(correct))


def load_set(now):
    """按星期加载对应题库文件，按 ISO 周数在 4 套中轮换。"""
    path = os.path.join(DATA_DIR, WEEKDAY_FILES[now.weekday()])
    with open(path, encoding="utf-8") as f:
        sets = json.load(f)["sets"]
    s = sets[now.isocalendar()[1] % len(sets)]
    shuffle_options(s, now)
    return s


def load_shenlun(now):
    """申论素材按日期在年内序数取模，28 条循环。"""
    with open(os.path.join(DATA_DIR, "shenlun.json"), encoding="utf-8") as f:
        items = json.load(f)["items"]
    return items[now.timetuple().tm_yday % len(items)]


def format_questions(questions):
    """输出题目行；答案与解析单独返回，放在文末。"""
    lines, answers = [], []
    for i, q in enumerate(questions, 1):
        opts = "  ".join(f"{chr(64 + j)}.{opt}" for j, opt in enumerate(q["options"], 1))
        lines.append(f"{i}. {q['stem']}\n   {opts}")
        answers.append(f"{i}. {q['answer']}　{q['explain']}")
    return "\n".join(lines), "\n".join(answers)


def build_body(now):
    """组装打卡卡正文（纯文本，换行分隔）。"""
    news = pick_news(fetch_news())
    s = load_set(now)
    material = s.get("material")
    questions, answers = format_questions(s["questions"])
    shenlun = load_shenlun(now)
    date_str = f"{now.month}月{now.day}日"

    parts = [f"【今日时政 · {date_str}】"]
    if news:
        parts.extend(f"{i}. {n}" for i, n in enumerate(news, 1))
        parts.append("（提示：关注数据、政策表述、地点与意义三要素，常考常识判断）")
    else:
        parts.append("今日新闻源暂时不可用，请通过学习强国APP补充时政积累。")

    parts.append("\n【今日打卡任务】\n" + " | ".join(TASKS))

    parts.append(f"\n【今日小练 · {EXERCISE_LABELS[now.weekday()]}（第{s['week']}套）】")
    if material:
        parts.append(f"材料：{material}")
    parts.append(questions)

    parts.append(f"\n【申论素材 · {shenlun['theme']}】")
    parts.append(f"观点：{shenlun['viewpoint']}")
    parts.append(f"案例：{shenlun['case']}")
    parts.append(f"规范词：{shenlun['terms']}")

    parts.append("\n——— 今日答案（先做题再看）———\n" + answers)
    return "\n".join(parts)


def send_bark(title, body):
    """调用 Bark 推送接口。"""
    key = os.environ.get("BARK_DEVICE_KEY")
    if not key:
        print("错误：未设置 BARK_DEVICE_KEY 环境变量（GitHub Secrets 中配置）")
        sys.exit(1)
    server = os.environ.get("BARK_SERVER", "https://api.day.app").rstrip("/")
    payload = json.dumps({"device_key": key, "title": title, "body": body, "group": "省考打卡"}).encode("utf-8")
    req = urllib.request.Request(
        f"{server}/push", data=payload, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") == 200:
        print("推送成功")
    else:
        print(f"推送失败：{result}")
        sys.exit(1)


def main():
    now = datetime.now(CST)
    title = f"省考打卡卡 {now.month}月{now.day}日 {WEEKDAY_NAMES[now.weekday()]}"
    body = build_body(now)
    if "--dry-run" in sys.argv:
        print(f"标题：{title}\n{'=' * 30}\n{body}")
        return
    send_bark(title, body)


if __name__ == "__main__":
    main()
