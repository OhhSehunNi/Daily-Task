# -*- coding: utf-8 -*-
"""行测申论每日学习云端推送脚本（仅使用 Python 标准库，GitHub Actions 无需安装依赖）。

流程：抓取当日新闻（全国政策为主线）-> 加载当月题库 -> 组装每日学习内容 -> 通过 Bark 推送到 iPhone。
题库按月分目录存放（data/YYYY-MM），脚本按当月取值；当月目录不存在时回退到最新可用月份。
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
# 新闻相关度权重：全国性政策/时政为主线（权重高），广东/深圳本地新闻为辅线（权重低）
KEYWORD_WEIGHTS = {
    "国家": 3, "中央": 3, "国务院": 3, "政策": 3, "改革": 3, "法治": 3, "会议": 3,
    "高质量发展": 3, "新质生产力": 3, "乡村振兴": 3, "生态文明": 3,
    "经济": 2, "科技": 2, "民生": 2, "就业": 2, "教育": 2, "医疗": 2, "养老": 2,
    "外交": 2, "会晤": 2, "发展": 2, "建设": 2, "治理": 2, "数据": 2, "增长": 2,
    "金融": 2, "外贸": 2, "进出口": 2, "人工智能": 2, "安全": 2, "乡村": 2, "生态": 2,
    "广东": 1, "深圳": 1, "广州": 1, "大湾区": 1,
}
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


def resolve_data_dir(now):
    """定位当月题库目录 data/YYYY-MM；目录缺失或为空时回退到最新可用月份/根目录。"""
    month_dir = os.path.join(DATA_DIR, now.strftime("%Y-%m"))
    if _has_data(month_dir):
        return month_dir
    # 回退：取 data 下所有 YYYY-MM 目录中最新（字典序最大）且含数据的一个
    months = sorted(d for d in os.listdir(DATA_DIR)
                    if len(d) == 7 and d[4] == "-" and _has_data(os.path.join(DATA_DIR, d)))
    if months:
        return os.path.join(DATA_DIR, months[-1])
    return DATA_DIR  # 无月份目录时兼容旧的扁平结构


def _has_data(d):
    """判断目录存在且包含至少一个 json 数据文件。"""
    return os.path.isdir(d) and any(f.endswith(".json") for f in os.listdir(d))


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
    """按公考相关度加权打分排序，取前 n 条；全国政策为主线、广东/深圳本地为辅线。"""
    scored = [(sum(w for k, w in KEYWORD_WEIGHTS.items() if k in item), i, item)
              for i, item in enumerate(news)]
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
    path = os.path.join(resolve_data_dir(now), WEEKDAY_FILES[now.weekday()])
    with open(path, encoding="utf-8") as f:
        sets = json.load(f)["sets"]
    s = sets[now.isocalendar()[1] % len(sets)]
    shuffle_options(s, now)
    return s


def load_shenlun(now):
    """申论素材按日期在年内序数取模循环。"""
    with open(os.path.join(resolve_data_dir(now), "shenlun.json"), encoding="utf-8") as f:
        items = json.load(f)["items"]
    return items[now.timetuple().tm_yday % len(items)]


def load_knowledge(now):
    """加载每日知识点：常识判断 2 条 + 言语理解 2 条，按年内天数轮换。"""
    with open(os.path.join(resolve_data_dir(now), "knowledge.json"), encoding="utf-8") as f:
        data = json.load(f)
    day = now.timetuple().tm_yday
    common, lang = data["common_sense"], data["language"]
    # 每天取 2 条、步长为 2，避免相邻两天内容大量重复
    cs = [common[(day * 2) % len(common)], common[(day * 2 + 1) % len(common)]]
    lg = [lang[(day * 2) % len(lang)], lang[(day * 2 + 1) % len(lang)]]
    return {"common": cs, "language": lg}


def format_knowledge(know):
    """输出知识点文本：常识按「要点+考查角度+易错点」，言语按「释义+色彩+搭配+易混」。"""
    lines = ["【今日知识点】"]
    for k in know["common"]:
        lines.append(f"· {k['point']}：{k['detail']}")
        lines.append(f"　考查角度：{k['angle']}")
        lines.append(f"　易错点：{k['pitfall']}")
    for k in know["language"]:
        lines.append(f"· {k['word']}：{k['meaning']}")
        lines.append(f"　色彩：{k['tone']}｜搭配：{k['collocation']}")
        lines.append(f"　易混：{k['compare']}")
    return "\n".join(lines)


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

    parts.append("\n" + format_knowledge(load_knowledge(now)))

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
    # 注意用 or 兜底：若环境变量存在但为空串（Secret 未配置时 GitHub 会注入空值），也回退到默认服务器
    server = os.environ.get("BARK_SERVER") or "https://api.day.app"
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
