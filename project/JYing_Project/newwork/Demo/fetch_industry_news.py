#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多领域行业资讯每日抓取脚本
==========================

从公开 RSS / Atom 订阅与站点新闻列表页抓取 6 个领域的行业资讯：
人工智能、嵌入式/硬件、汽车/智能网联、机器人/具身智能、医疗科技、世界模型/端侧AI。

按日期归档为 CSV + TXT + Markdown，并生成可双击查看的网页，例如：

    D:\\AI\\DSHworkspace\\newwork\\worknews\\2026-11-04_news.csv
    D:\\AI\\DSHworkspace\\newwork\\worknews\\2026-11-04_news.txt
    D:\\AI\\DSHworkspace\\newwork\\worknews\\2026-11-04_news.md
    D:\\AI\\DSHworkspace\\newwork\\index.html        # 自包含网页，双击即看

特点
----
* 两种抓取方式：RSS/Atom 订阅；无 RSS 的中文站点按正则解析新闻列表页
* 只用 requests + 标准库(xml.etree / re)，无需额外安装 feedparser、bs4
* 多线程并发抓取，单源失败不影响整体，失败原因会在控制台与日志里列出
* 6 领域关键词表，综合媒体自动归类；垂直源直接归入所属领域
* 同一天重复运行会与已有 CSV 合并、按链接去重，不会覆盖丢失数据
* 跨天去重索引（.seen_urls.json）：同一篇文章不会连续多天重复出现
* 每次运行写日志到 <输出目录>/logs/fetch_YYYY-MM-DD.log
* 每次运行重新生成 index.html：数据内嵌在页面里，无需服务器、无跨域问题

用法
----
    python fetch_industry_news.py                 # 抓取并保存今天的文件
    python fetch_industry_news.py --days 7        # 最近 7 天的内容
    python fetch_industry_news.py --list-sources  # 只看源列表
    python fetch_industry_news.py --date 2026-11-04 --days 1
    python fetch_industry_news.py --no-html       # 只抓数据，不更新网页
    python fetch_industry_news.py --no-seen-index # 关闭跨天去重

定时运行：已注册 Windows 任务计划 "AI_Embedded_DailyNews"，每天 09:30 执行
（电脑关机时该次跳过，不补跑）。详见 README.md。

退出码：0 = 成功抓到数据；1 = 所有源都失败 / 无数据。
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

# --------------------------------------------------------------------------- #
# 基本配置
# --------------------------------------------------------------------------- #

# 默认输出目录：<脚本所在目录>/../worknews，跟随文件夹走，方便整个目录复制给别人
# 也可以用 --output-dir 或环境变量 NEWS_OUTPUT_DIR 覆盖
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = Path(os.environ.get(
    "NEWS_OUTPUT_DIR", str(_PROJECT_ROOT / "worknews")
))

# --------------------------------------------------------------------------- #
# 领域体系：6 个领域
# --------------------------------------------------------------------------- #

# 领域 key -> (显示名, 数字序号)
# 领域元数据：key -> 显示名 / 短标签 / 浅色主题色 / 深色主题色
DOMAIN_META: dict[str, dict[str, str]] = {
    "ai":       {"label": "人工智能", "short": "AI", "light": "#4c6ef5", "dark": "#8fa9ff"},
    "embedded": {"label": "嵌入式/硬件", "short": "嵌入式", "light": "#0b7285", "dark": "#63e6be"},
    "auto":     {"label": "汽车/智能网联", "short": "汽车", "light": "#e8590c", "dark": "#ffa94d"},
    "robot":    {"label": "机器人/具身智能", "short": "机器人", "light": "#ae3ec9", "dark": "#e599f7"},
    "medical":  {"label": "医疗科技", "short": "医疗", "light": "#2f9e44", "dark": "#8ce99a"},
    "frontier": {"label": "世界模型/端侧AI", "short": "前沿", "light": "#6741d9", "dark": "#b197fc"},
}

DOMAINS: dict[str, str] = {key: meta["label"] for key, meta in DOMAIN_META.items()}
DOMAIN_ORDER: tuple[str, ...] = tuple(DOMAIN_META)

# 显示名 -> 领域 key（CSV 里存的是显示名）
_LABEL_TO_KEY: dict[str, str] = {label: key for key, label in DOMAINS.items()}

# 兼容旧版本 CSV 的分类名
_LEGACY_CATEGORY_MAP = {
    "嵌入式/半导体": "embedded",
    "AI": "ai",
    "人工智能 (AI)": "ai",
    "嵌入式 / 半导体": "embedded",
}


def domain_of(raw: str) -> str:
    """把 CSV 中的领域名 / 旧分类名 / 领域 key 归一到 6 领域之一。"""

    if not raw:
        return "ai"
    raw = raw.strip()
    if raw in DOMAINS:          # 已经是 key
        return raw
    if raw in _LABEL_TO_KEY:    # 新版本的显示名
        return _LABEL_TO_KEY[raw]
    return _LEGACY_CATEGORY_MAP.get(raw, "ai")


def domain_label(key: str) -> str:
    return DOMAINS.get(key, DOMAINS["ai"])


CATEGORY_AI = "人工智能"          # 旧常量保留，减少外部引用破坏
CATEGORY_EMBEDDED = "嵌入式/半导体"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


@dataclass(frozen=True)
class Source:
    """一个资讯源。

    kind:
      rss  - RSS/Atom 订阅，url 为订阅地址
      html - 列表页抓取，url 为新闻列表页，靠 item/link/title/date 三个正则提取
    """

    name: str
    url: str
    domain: str = "ai"
    strict: bool = True   # True=垂直源全量收录; False=综合源按关键词筛选再归类
    kind: str = "rss"
    item_re: str = ""     # 匹配文章链接（相对或绝对）
    title_re: str = r'>([^<>]{10,120})<'   # 从 item 块中提取标题
    date_re: str = ""     # 从 item 块中提取日期文本
    as_date: bool = False  # True=日期直接写在 URL 里（yyyy-MM）
    limit_domains: tuple[str, ...] = ()  # 综合源只允许归入这些领域（空=不限）
    note: str = ""


# ---------------------------------------------------------------
# RSS 源（沿用原有，标注领域）
# ---------------------------------------------------------------
SOURCES: tuple[Source, ...] = (
    # ---------------- 人工智能 ----------------
    Source("量子位", "https://www.qbitai.com/feed", "ai"),
    Source("OpenAI", "https://openai.com/blog/rss.xml", "ai"),
    Source("Google AI", "https://blog.google/technology/ai/rss/", "ai"),
    Source("Google DeepMind", "https://deepmind.google/blog/rss.xml", "ai"),
    Source("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/", "ai"),
    Source("BAIR (Berkeley)", "https://bair.berkeley.edu/blog/feed.xml", "ai"),
    Source("MarkTechPost", "https://www.marktechpost.com/feed/", "ai"),
    Source("36氪", "https://www.36kr.com/feed", "ai", strict=False),
    Source("极客公园", "https://www.geekpark.net/rss", "ai", strict=False),
    Source("钛媒体", "https://www.tmtpost.com/rss.xml", "ai", strict=False),
    Source("InfoQ 中文", "https://www.infoq.cn/feed", "ai", strict=False),
    Source("雷峰网", "https://www.leiphone.com/feed", "ai", strict=False),
    Source("IT之家", "https://www.ithome.com/rss/", "ai", strict=False),
    Source("The Verge", "https://www.theverge.com/rss/index.xml", "ai", strict=False),

    # ---------------- 嵌入式 / 硬件 ----------------
    Source("CNX Software", "https://www.cnx-software.com/feed/", "embedded"),
    Source("Hackaday", "https://hackaday.com/feed/", "embedded"),
    Source("Embedded.com", "https://www.embedded.com/feed/", "embedded"),
    Source("EE Times", "https://www.eetimes.com/feed/", "embedded", strict=False),
    Source("EE Journal", "https://www.eejournal.com/feed/", "embedded"),
    Source("Adafruit Blog", "https://blog.adafruit.com/feed/", "embedded"),
    Source("Edge AI & Vision", "https://www.edge-ai-vision.com/feed/", "frontier"),
    Source("Semiconductor Digest", "https://www.semiconductor-digest.com/feed/", "embedded"),
    Source("RT Insights (边缘AI)", "https://www.rtinsights.com/feed/", "frontier"),
    Source("DIGITIMES", "https://www.digitimes.com/rss/daily.xml", "embedded", strict=False),
    Source("Tom's Hardware", "https://www.tomshardware.com/feeds/all", "embedded", strict=False),

    # ---------------- 汽车与智能网联 ----------------
    Source("第一电动网", "https://www.d1ev.com/", "auto", kind="html",
           item_re=r'href="(/news/[a-z]+/\d+)"',
           title_re=r'>([^<>]{12,120})<',
           date_re=r'(\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}日)'),
    Source("盖世汽车", "https://auto.gasgoo.com/", "auto", kind="html",
           item_re=r'href="(https://auto\.gasgoo\.com/news/[^"]+\.shtml)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r'/news/(20\d{2}-\d{2})/'),

    # ---------------- 机器人 / 具身智能 ----------------
    Source("具身之家", "https://www.jushenhome.com/news", "robot", kind="html",
           item_re=r'href="(/news/\d+)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r'(20\d{2}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)'),

    # ---------------- 嵌入式（中文站点，HTML） ----------------
    Source("21ic 电子网", "https://www.21ic.com/news/", "embedded", kind="html",
           item_re=r'href="(/a/\d+\.html)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r'(20\d{2}-\d{2}-\d{2})'),
    Source("电子发烧友", "https://www.elecfans.com/news/", "embedded", kind="html",
           item_re=r'href="(https://www\.elecfans\.com/d/\d+\.html)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r''),

    # ---------------- 医疗科技 ----------------
    Source("OFweek 医械", "https://www.ofweek.com/medical/", "medical", kind="html",
           item_re=r'href="([^"]*/medical/20\d{2}-\d{2}/ART-[^"]+\.html)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r'/medical/(20\d{2}-\d{2})-',
           as_date=True),
    # 医疗经济学（Medical Economics）的医疗器械/技术专题：/view/ 是文章页
    Source("Medical Economics", "https://www.medicaleconomics.com/topics/med-tech", "medical",
           kind="html",
           item_re=r'href="(/view/[^"]+)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r''),

    # ---------------- 世界模型 / 端侧 AI ----------------
    Source("Edge AI Foundation", "https://www.edgeaifoundation.org/", "frontier", kind="html",
           item_re=r'href="(/posts/[^"#?]+)"',
           title_re=r'>([^<>]{10,120})<',
           date_re=r''),
)


# 关键词表：ASCII 词按整词匹配，中文词按子串匹配；key=领域 key
AI_KEYWORDS: tuple[str, ...] = (
    "AI", "AIGC", "AGI", "LLM", "GPT", "ChatGPT", "OpenAI", "Anthropic", "Claude",
    "Gemini", "DeepSeek", "Copilot", "Midjourney", "Stable Diffusion", "NVIDIA",
    "英伟达", "GPU", "TPU", "NPU", "Transformer", "RAG", "Agent",
    "人工智能", "大模型", "机器学习", "深度学习", "神经网络", "生成式", "智能体",
    "多模态", "具身智能", "算力", "推理", "微调", "提示词", "强化学习",
    "计算机视觉", "语音识别", "自然语言处理", "扩散模型", "模型训练", "AI芯片",
)

EMBEDDED_KEYWORDS: tuple[str, ...] = (
    "MCU", "MPU", "SoC", "RTOS", "FreeRTOS", "Zephyr", "FPGA", "CPLD", "RISC-V",
    "ARM", "Cortex", "STM32", "ESP32", "ESP8266", "Raspberry Pi", "Arduino",
    "Jetson", "PLC", "BSP", "PCB", "EDA", "ADC", "DAC", "SPI", "I2C", "UART",
    "MIPI", "LoRa", "Zigbee", "NB-IoT", "Wi-Fi", "Bluetooth", "USB",
    "嵌入式", "单片机", "微控制器", "开发板", "传感器", "物联网", "固件",
    "实时操作系统", "嵌入式Linux", "驱动程序", "边缘计算", "工业控制",
    "电源管理", "半导体", "晶圆", "封装测试", "制程",
    "光刻", "存储器", "低功耗", "无线通信", "毫米波", "以太网", "开源硬件",
    "树莓派", "芯片", "总线",
)

AUTO_KEYWORDS: tuple[str, ...] = (
    "智能驾驶", "自动驾驶", "辅助驾驶", "NOA", "智驾", "座舱", "智能座舱",
    "车机", "车联网", "V2X", "激光雷达", "线控", "域控制器", "整车",
    "新能源车", "电动汽车", "电动车", "三电", "充电桩",
    "混动", "增程", "电驱", "动力电池", "固态电池", "电池包", "补能",
    "汽车", "车企", "主机厂", "乘联会", "车规", "汽车电子", "车载",
    "Tesla", "BYD", "比亚迪", "蔚来", "理想汽车", "小鹏", "小米汽车", "问界",
    "BEV", "PHEV", "ADAS", "L2", "L3",
)

ROBOT_KEYWORDS: tuple[str, ...] = (
    "机器人", "人形机器人", "具身智能", "具身", "机械臂", "协作机器人",
    "四足机器人", "机器狗", "狗形机器人", "外骨骼", "遥操作",
    "灵巧手", "触觉传感器", "关节模组", "减速器", "伺服", "运动控制",
    "波士顿动力", "宇树", "Unitree", "特斯拉Optimus", "Optimus",
    "Figure", "Agility", "机器人产业", "机器人融资", "Robot",
    "Robotics", "humanoid",
)

MEDICAL_KEYWORDS: tuple[str, ...] = (
    "医疗器械", "医疗设备", "医疗科技", "医疗AI", "手术机器人", "影像设备",
    "CT", "MRI", "超声", "内窥镜", "脑机接口", "植入", "起搏器",
    "药物研发", "新药", "临床试验", "FDA", "NMPA", "获批上市", "创新医疗器械",
    "体外诊断", "IVD", "监护仪", "呼吸机", "骨科", "心血管", "血管介入",
    "医美", "远程医疗", "数字医疗", "医药", "医疗", "器械", "诊断",
    "brain-computer", "medical device", "medtech",
)

FRONTIER_KEYWORDS: tuple[str, ...] = (
    "世界模型", "World Model", "端侧AI", "端侧大模型", "边缘AI", "TinyML",
    "具身大模型", "空间智能", "物理AI", "Physical AI", "世界模拟器",
    "视频生成模型", "生成式物理", "VLA", "视觉语言动作", "生成式世界",
    "轻量化模型", "端云一体", "车载大模型", "机器人基础模型",
    "Genie", "Sora", "Cosmos", "JEPA",
)

KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai": AI_KEYWORDS,
    "embedded": EMBEDDED_KEYWORDS,
    "auto": AUTO_KEYWORDS,
    "robot": ROBOT_KEYWORDS,
    "medical": MEDICAL_KEYWORDS,
    "frontier": FRONTIER_KEYWORDS,
}

CSV_HEADER = ["日期", "领域", "来源", "标题", "摘要", "链接", "发布时间"]

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "source", "ref", "share_token", "fbclid", "gclid", "mc_cid",
}

LOG = logging.getLogger("news")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def local_now() -> datetime:
    """带本地时区的当前时间。"""

    return datetime.now().astimezone()


def setup_console() -> None:
    """Windows 控制台中文输出兜底。"""

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_JUNK_SUMMARY_RE = re.compile(r"^\s*(点击)?(查看|阅读)原文\s*>?\s*$")
_BARE_AMP_RE = re.compile(
    r"&(?!(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#x[0-9a-fA-F]{1,6});)"
)
_BAD_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def strip_html(raw: str, limit: int = 240) -> str:
    """去标签、反转义、压缩空白并截断。"""

    if not raw:
        return ""
    # 有些源把 CDATA 标记本身转义成了普通文本（&lt;![CDATA[ ... ]]&gt;）
    text = raw.replace("<![CDATA[", "").replace("]]>", "")
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    """解析 RSS/Atom 里各种日期写法，统一转成本地带时区时间。"""

    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None

    dt: Optional[datetime] = None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        dt = None

    if dt is None:
        candidate = value.replace("Z", "+00:00").replace("z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            dt = None

    if dt is None:
        for fmt in (
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y年%m月%d日",
            "%Y-%m-%dT%H:%M:%S", "%d %b %Y %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_now().tzinfo)
    dt = dt.astimezone(local_now().tzinfo)
    # 个别中文源会把 +08:00 的时间当 UTC 输出，导致"未来时间"；先按 8 小时回拨，
    # 仍不合法就截断到当前时刻，避免日报出现明显错误的发布时间
    now = local_now()
    if dt > now + timedelta(hours=2):
        shifted = dt - timedelta(hours=8)
        dt = shifted if shifted <= now else now
    return dt


def normalize_url(url: str) -> str:
    """去掉锚点与跟踪参数，便于去重。"""

    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS]
    result = urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/") or "/",
        urlencode(query),
        "",
    ))
    return result


def dedupe_key(item: dict) -> str:
    if item.get("link"):
        return "url:" + normalize_url(item["link"])
    title = re.sub(r"\s+", "", item.get("title", "")).lower()
    return "title:" + title


def match_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    """返回命中的关键词；ASCII 词要求整词边界，中文词按子串。"""

    hits: list[str] = []
    if not text:
        return hits
    lowered = text.lower()
    for kw in keywords:
        if not kw:
            continue
        if kw.isascii():
            pattern = rf"(?<![a-z0-9]){re.escape(kw.lower())}(?![a-z0-9])"
            if re.search(pattern, lowered):
                hits.append(kw)
        elif kw in text:
            hits.append(kw)
    return hits


# --------------------------------------------------------------------------- #
# RSS / Atom 解析
# --------------------------------------------------------------------------- #

def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _child_text(node: ET.Element, *names: str) -> str:
    """按标签名（忽略命名空间）取第一个非空文本的子节点。"""

    wanted = {n.lower() for n in names}
    for child in node:
        if _localname(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _child_link(node: ET.Element) -> str:
    """兼容 RSS 的 <link>text</link> 与 Atom 的 <link href=... rel=alternate/>。"""

    fallback = ""
    for child in node:
        if _localname(child.tag) != "link":
            continue
        href = (child.get("href") or "").strip()
        rel = (child.get("rel") or "alternate").lower()
        if href:
            if rel == "alternate":
                return href
            fallback = fallback or href
        else:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return fallback


def parse_feed(raw: bytes, source_name: str) -> list[dict]:
    """把 XML 字节解析成条目列表。失败抛 ValueError。"""

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # 部分中文源存在非法字符或裸 &，清洗后重试一次
        text = raw.decode("utf-8", errors="replace")
        text = _BAD_XML_CHARS_RE.sub("", text)
        text = _BARE_AMP_RE.sub("&amp;", text)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError(f"XML 解析失败: {exc}") from exc

    items: list[dict] = []
    for node in root.iter():
        if _localname(node.tag) not in ("item", "entry"):
            continue

        title = strip_html(_child_text(node, "title"), limit=0)
        if not title:
            continue

        link = _child_link(node)
        summary_raw = _child_text(node, "description", "summary", "content", "encoded")
        summary = strip_html(summary_raw)
        if _JUNK_SUMMARY_RE.match(summary):  # "点击查看原文" 之类的空壳摘要
            summary = ""
        published_raw = _child_text(
            node, "pubdate", "published", "updated", "date", "created", "lastbuilddate"
        )
        published = parse_datetime(published_raw)

        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published": published,
        })

    return items


# --------------------------------------------------------------------------- #
# 抓取
# --------------------------------------------------------------------------- #

@dataclass
class FetchResult:
    source: Source
    items: list[dict] = field(default_factory=list)
    error: str = ""
    total: int = 0
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.error


def http_get(url: str, timeout: float, retries: int = 2, accept: str = "") -> requests.Response:
    """带重试与随机 UA 的 GET。"""

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        headers = {
            "User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)],
            "Accept": accept or ("application/rss+xml, application/atom+xml, application/xml, "
                                 "text/xml;q=0.9, */*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }
        try:
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return response
            last_exc = requests.HTTPError(f"HTTP {response.status_code}")
            if response.status_code in (403, 404, 410):
                break  # 这类状态重试也没用
        except requests.RequestException as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(1.2 * (attempt + 1))
    raise last_exc or RuntimeError("未知网络错误")


# --------------------------------------------------------------------------- #
# HTML 列表页解析（无 RSS 的中文站点）
# --------------------------------------------------------------------------- #

_META_CHARSET_RE = re.compile(rb'charset=["\']?([\w-]+)', re.I)


def decode_html(response: requests.Response) -> str:
    """按响应头 / meta 推断编码解码；兜底 utf-8、gb18030。"""

    encoding = (response.encoding or "").lower()
    if not encoding or encoding in ("iso-8859-1", "ascii"):
        match = _META_CHARSET_RE.search(response.content[:4096])
        encoding = match.group(1).decode("ascii", "ignore") if match else ""

    for enc in (encoding, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            return response.content.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return response.content.decode("utf-8", errors="replace")


def _anchor_title(html_text: str, href_match: re.Match) -> tuple[str, int]:
    """从 <a> 标签提取标题：title 属性 > 标签内文本 > alt 属性。

    返回 (标题, 标签起点)，标签起点用于截取"条目块"提取日期。
    """

    tag_start = html_text.rfind("<a", 0, href_match.start() + 1)
    tag_end = html_text.find(">", href_match.end())
    if tag_start < 0 or tag_end < 0:
        return "", href_match.start()

    tag = html_text[tag_start:tag_end + 1]
    inner_end = html_text.find("</a>", tag_end)
    inner = html_text[tag_end + 1:inner_end] if inner_end > 0 else ""

    candidates: list[str] = []
    for attr in ("title", "alt"):
        found = re.search(rf'{attr}=["\']([^"\']{{8,160}})["\']', tag)
        if found:
            candidates.append(found.group(1))
    inner_text = strip_html(inner, limit=0)
    if inner_text:
        candidates.append(inner_text)

    for cand in candidates:
        clean = strip_html(cand, limit=0)
        if len(clean) >= 8:
            return clean, tag_start
    return "", tag_start


def parse_html_list(html_text: str, src: Source) -> list[dict]:
    """按 Source 中配置的正则，从列表页 HTML 提取条目。"""

    items: list[dict] = []
    seen: set[str] = set()
    if not src.item_re:
        raise ValueError("HTML 源缺少 item_re 配置")

    for match in re.finditer(src.item_re, html_text):
        href = (match.group(1) or "").strip()
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue
        link = urljoin(src.url, href)
        if link in seen:
            continue

        title, tag_start = _anchor_title(html_text, match)
        if not title:
            continue

        published: Optional[datetime] = None
        if src.date_re:
            block = html_text[max(0, tag_start - 600):match.end() + 900]
            date_match = re.search(src.date_re, block)
            if date_match:
                published = parse_datetime(date_match.group(1))

        seen.add(link)
        items.append({
            "title": title,
            "link": link,
            "summary": "",
            "published": published,
        })

    return items


def classify(text: str, default_domain: str,
             allowed: tuple[str, ...] = ()) -> str:
    """按关键词给综合源的条目归类；无命中返回空串（丢弃）。"""

    scores = {key: len(match_keywords(text, KEYWORDS[key]))
              for key in (allowed or DOMAIN_ORDER)}
    best = max(scores.values(), default=0)
    if best <= 0:
        return ""
    winners = [key for key, score in scores.items() if score == best]
    return default_domain if default_domain in winners else winners[0]


def fetch_source(src: Source, *, timeout: float, days: int,
                 max_items: int, cutoff: datetime, retries: int) -> FetchResult:
    started = time.perf_counter()
    result = FetchResult(source=src)
    try:
        accept = ("text/html,application/xhtml+xml,*/*;q=0.8"
                  if src.kind == "html" else "")
        response = http_get(src.url, timeout=timeout, retries=retries, accept=accept)
        if src.kind == "html":
            raw_items = parse_html_list(decode_html(response), src)
        else:
            raw_items = parse_feed(response.content, src.name)
    except Exception as exc:  # noqa: BLE001 - 单源失败必须不影响整体
        result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed = time.perf_counter() - started
        return result

    result.total = len(raw_items)
    kept: list[dict] = []
    seen: set[str] = set()

    for raw in raw_items:
        published = raw.get("published")
        # 列表页没有稳定时间字段，不做时间窗过滤（列表本身只展示近期内容）
        if src.kind != "html" and published is not None and published < cutoff:
            continue

        title = raw["title"]
        summary = raw["summary"]
        text = f"{title} {summary}"

        if src.strict:
            domain = src.domain
        else:
            domain = classify(text, src.domain, src.limit_domains)
            if not domain:
                continue

        item = {
            "domain": domain,
            "source": src.name,
            "title": title,
            "summary": summary,
            "link": raw["link"],
            "published": published,
        }
        key = dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)

    kept.sort(key=lambda x: x["published"] or datetime.min.replace(tzinfo=local_now().tzinfo),
              reverse=True)
    result.items = kept[:max_items]
    result.elapsed = time.perf_counter() - started
    return result


def _sort_key(item: dict) -> tuple[int, float]:
    domain = item.get("domain", "ai")
    return (DOMAIN_ORDER.index(domain) if domain in DOMAIN_ORDER else 99,
            -(item["published"].timestamp() if item.get("published") else 0))


def collect(results: Iterable[FetchResult]) -> list[dict]:
    """跨源去重（链接 + 标题）并排序。"""

    rows: list[dict] = []
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    for result in results:
        for item in result.items:
            key = dedupe_key(item)
            if key in seen_links:
                continue
            title_key = re.sub(r"[\s\W_]+", "", item.get("title", "")).lower()
            if len(title_key) > 12 and title_key in seen_titles:
                continue  # 同一篇通稿被多个站点转载
            seen_links.add(key)
            seen_titles.add(title_key)
            rows.append(item)
    rows.sort(key=_sort_key)
    return rows


# --------------------------------------------------------------------------- #
# 保存
# --------------------------------------------------------------------------- #

def read_existing(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                published = parse_datetime(row.get("发布时间", ""))
                raw_domain = row.get("领域") or row.get("分类") or ""
                rows.append({
                    "domain": domain_of(raw_domain),
                    "source": row.get("来源", ""),
                    "title": row.get("标题", ""),
                    "summary": row.get("摘要", ""),
                    "link": row.get("链接", ""),
                    "published": published,
                })
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        LOG.warning("读取已有 CSV 失败，将重建：%s", exc)
        return []
    return rows


def merge_rows(old: list[dict], new: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in list(old) + list(new):
        if not item.get("title"):
            continue
        key = dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged.sort(key=_sort_key)
    return merged


def fmt_time(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "未知"


def write_csv(rows: list[dict], path: Path, day: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow([
                day,
                domain_label(row["domain"]),
                row["source"],
                row["title"],
                row["summary"],
                row["link"],
                fmt_time(row["published"]),
            ])
    tmp.replace(path)


CN_DIGITS = "一二三四五六七八九十"


def _by_domain(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {key: [] for key in DOMAIN_ORDER}
    for row in rows:
        grouped.setdefault(row["domain"], []).append(row)
    return grouped


def _domain_summary(grouped: dict[str, list[dict]]) -> str:
    parts = [f"{DOMAINS[key]} {len(items)}" for key, items in grouped.items() if items]
    return " / ".join(parts) if parts else "无"


def write_txt(rows: list[dict], path: Path, day: str, stats: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = local_now()
    grouped = _by_domain(rows)

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"多领域行业资讯日报  {day}")
    lines.append("=" * 72)
    lines.append(f"生成时间 : {now.strftime('%Y-%m-%d %H:%M:%S')} (UTC{now.strftime('%z')})")
    lines.append(f"条目总数 : {len(rows)}  ({_domain_summary(grouped)})")
    lines.append("数据来源 : 公开 RSS / Atom + 站点列表页")
    if stats:
        lines.append("")
        lines.extend(stats)
    lines.append("")

    for index, key in enumerate(DOMAIN_ORDER):
        section_rows = grouped.get(key, [])
        marker = CN_DIGITS[index] if index < len(CN_DIGITS) else str(index + 1)
        lines.append("")
        lines.append("-" * 72)
        lines.append(f"{marker}、{DOMAINS[key]}  共 {len(section_rows)} 条")
        lines.append("-" * 72)
        if not section_rows:
            lines.append("（本时段无新内容）")
            continue
        for idx, row in enumerate(section_rows, 1):
            lines.append(f"{idx}. {row['title']}")
            lines.append(f"   来源: {row['source']}  |  发布: {fmt_time(row['published'])}")
            if row["summary"]:
                lines.append(f"   摘要: {row['summary']}")
            if row["link"]:
                lines.append(f"   链接: {row['link']}")
            lines.append("")

    lines.append("=" * 72)
    lines.append("说明: 内容由脚本自动抓取，版权归原站点所有；请以原文链接为准。")
    lines.append("=" * 72)

    path.write_text("\n".join(lines), encoding="utf-8")


def write_markdown(rows: list[dict], path: Path, day: str, stats: list[str]) -> None:
    """Markdown 版本，方便粘贴到笔记 / 博客 / 仓库。"""

    now = local_now()
    grouped = _by_domain(rows)

    out: list[str] = [
        f"# 多领域行业资讯日报 · {day}",
        "",
        f"- 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')} (UTC{now.strftime('%z')})",
        f"- 条目总数：{len(rows)}（{_domain_summary(grouped)}）",
    ]
    out.extend(f"- {line}" for line in stats)
    out.append("")

    for index, key in enumerate(DOMAIN_ORDER):
        items = grouped.get(key, [])
        marker = CN_DIGITS[index] if index < len(CN_DIGITS) else str(index + 1)
        out.append(f"## {marker}、{DOMAINS[key]}（{len(items)} 条）")
        out.append("")
        if not items:
            out.extend(["_本时段无新内容_", ""])
            continue
        for idx, row in enumerate(items, 1):
            link = f"[{row['title']}]({row['link']})" if row["link"] else row["title"]
            out.append(f"{idx}. {link}")
            out.append(f"   <sub>{row['source']} · {fmt_time(row['published'])}</sub>")
            if row["summary"]:
                out.append(f"   > {row['summary']}")
            out.append("")

    out.extend(["---", "", "内容由脚本自动抓取，版权归原站点所有。", ""])
    path.write_text("\n".join(out), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 网页生成（自包含，双击即可打开）
# --------------------------------------------------------------------------- #

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>多领域行业资讯</title>
<style>
*,*::before,*::after{box-sizing:border-box}
:root{
  color-scheme:light;
  --bg:#f4f6f9;--bg-soft:#e8ecf2;--panel:#ffffff;--panel-2:#fbfcfd;
  --text:#14181f;--text-2:#4a5464;--muted:#7d8798;
  --line:#e2e7ee;--line-2:#cdd5e0;
  --accent:#3b5bdb;--accent-2:#4c6ef5;
  --shadow:0 1px 2px rgba(16,24,40,.05),0 12px 28px -18px rgba(16,24,40,.4);
  --radius:16px;
}
html[data-theme="dark"]{
  color-scheme:dark;
  --bg:#0a0d12;--bg-soft:#11161f;--panel:#11161f;--panel-2:#151b26;
  --text:#e8eef6;--text-2:#a9b4c4;--muted:#7c8798;
  --line:#1f2633;--line-2:#2c3547;
  --accent:#7c9cff;--accent-2:#9db7ff;
  --shadow:0 1px 2px rgba(0,0,0,.5),0 16px 36px -20px rgba(0,0,0,.9);
}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--bg);color:var(--text);
  font:16px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC","Hiragino Sans GB",sans-serif;
  -webkit-font-smoothing:antialiased;transition:background .25s ease,color .25s ease;
}
body::before{
  content:"";position:fixed;left:0;right:0;top:0;height:480px;z-index:0;pointer-events:none;
  background:
    radial-gradient(620px 300px at 12% -10%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 70%),
    radial-gradient(520px 260px at 88% 0%, color-mix(in srgb, #22b8cf 13%, transparent), transparent 70%);
}
.wrap{width:min(1080px,calc(100% - 40px));margin:0 auto;position:relative;z-index:1}
a{color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}

/* ---------- 顶栏 ---------- */
.topbar{
  position:sticky;top:0;z-index:20;
  background:var(--bg);
  background:color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter:blur(14px) saturate(1.5);
  -webkit-backdrop-filter:blur(14px) saturate(1.5);
  border-bottom:1px solid var(--line);
}
.topbar-inner{display:flex;align-items:center;gap:16px;height:64px}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:15px;letter-spacing:.02em;text-decoration:none;white-space:nowrap}
.logo{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;color:#fff;font-size:12px;
  background:linear-gradient(135deg,var(--accent),#22b8cf)}
.tools{margin-left:auto;display:flex;align-items:center;gap:10px;min-width:0}
.search{position:relative;display:flex;align-items:center}
.search svg{position:absolute;left:11px;width:16px;height:16px;color:var(--muted);pointer-events:none}
.search input{
  width:250px;height:38px;padding:0 40px 0 34px;font-size:14px;font-family:inherit;
  color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:10px;
  outline:none;transition:border-color .15s,box-shadow .15s,background .2s;
}
.search input::placeholder{color:var(--muted)}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent)}
.search kbd{
  position:absolute;right:9px;font:11px/1 ui-monospace,SFMono-Regular,Consolas,monospace;
  color:var(--muted);background:var(--bg-soft);border:1px solid var(--line);border-radius:5px;padding:3px 5px;
}
select#day{
  height:38px;padding:0 30px 0 12px;font-size:14px;font-family:inherit;color:var(--text);
  background-color:var(--panel);border:1px solid var(--line);border-radius:10px;cursor:pointer;
  appearance:none;-webkit-appearance:none;
  background-image:linear-gradient(45deg,transparent 50%,var(--muted) 50%),linear-gradient(135deg,var(--muted) 50%,transparent 50%);
  background-position:calc(100% - 16px) 17px,calc(100% - 11px) 17px;
  background-size:5px 5px,5px 5px;background-repeat:no-repeat;
  transition:border-color .15s;
}
select#day:hover{border-color:var(--line-2)}
.icon-btn{
  width:38px;height:38px;display:grid;place-items:center;cursor:pointer;
  color:var(--text-2);background:var(--panel);border:1px solid var(--line);border-radius:10px;
  transition:color .15s,border-color .15s,background .15s;
}
.icon-btn:hover{color:var(--text);border-color:var(--line-2);background:var(--panel-2)}

/* ---------- 头部 ---------- */
.hero{padding:38px 0 6px}
.hero h1{
  margin:0 0 8px;font-size:clamp(24px,3.4vw,34px);line-height:1.25;letter-spacing:-.02em;
  background:linear-gradient(115deg,var(--text) 30%,var(--accent) 95%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.sub{margin:0;color:var(--muted);font-size:13.5px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0 4px}
.stat{
  display:flex;flex-direction:column;gap:1px;min-width:92px;padding:10px 14px;
  background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);
}
.stat b{font-size:20px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}
.stat i{font-style:normal;font-size:12px;color:var(--muted)}
.stat-domains b{font-size:15px;letter-spacing:.02em}

/* ---------- 分类 ---------- */
.tabs{display:flex;gap:4px;margin:22px 0 18px;padding:5px;width:max-content;max-width:100%;overflow-x:auto;
  background:var(--bg-soft);border:1px solid var(--line);border-radius:12px}
.tab{
  display:flex;align-items:center;gap:7px;padding:8px 14px;border:0;border-radius:9px;cursor:pointer;
  font:600 14px/1 inherit;color:var(--text-2);background:transparent;white-space:nowrap;
  transition:background .15s,color .15s,box-shadow .15s;
}
.tab:hover{color:var(--text)}
.tab.is-active{color:var(--text);background:var(--panel);box-shadow:var(--shadow)}
.tab em{
  font-style:normal;font-size:12px;font-weight:600;padding:1px 7px;border-radius:99px;
  color:var(--muted);background:var(--bg);
}
.tab.is-active em{color:var(--tab,var(--accent));background:color-mix(in srgb, var(--tab,var(--accent)) 12%, transparent)}

/* ---------- 列表 ---------- */
.list{display:grid;gap:12px;padding-bottom:34px}
.group{
  display:flex;align-items:center;gap:10px;margin:14px 2px 2px;
  font-size:12.5px;font-weight:600;letter-spacing:.12em;color:var(--muted);text-transform:uppercase;
}
.group::after{content:"";flex:1;height:1px;background:var(--line)}
.group .gdot{width:7px;height:7px;border-radius:99px;background:var(--d,var(--muted));flex:none}
.group .gcount{letter-spacing:0;font-weight:500;color:var(--muted)}
.group:first-child{margin-top:0}

.card{
  position:relative;overflow:hidden;padding:16px 18px 15px;
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);
  transition:transform .16s ease,border-color .16s ease;
  animation:rise .3s ease both;
}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.card{animation:none}}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--d-light,var(--accent));opacity:.9}
html[data-theme="dark"] .card::before{background:var(--d-dark,var(--accent))}
.card:hover{transform:translateY(-2px);border-color:var(--line-2)}
.card-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.badge{font-size:11px;font-weight:700;letter-spacing:.04em;padding:2.5px 8px;border-radius:99px;
  color:var(--d-light,var(--accent));
  background:color-mix(in srgb, var(--d-light,var(--accent)) 12%, transparent)}
html[data-theme="dark"] .badge{
  color:var(--d-dark,var(--accent));
  background:color-mix(in srgb, var(--d-dark,var(--accent)) 18%, transparent)}
.src{font-size:12.5px;font-weight:500;color:var(--text-2)}
.time{margin-left:auto;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.card h3{margin:2px 0 6px;font-size:17px;line-height:1.5;font-weight:600;letter-spacing:-.005em}
.card h3 a{text-decoration:none;color:var(--text);transition:color .15s}
.card h3 a:hover{color:var(--accent);text-decoration:underline;text-underline-offset:3px;text-decoration-thickness:1px}
.sum{
  margin:0;color:var(--text-2);font-size:14px;line-height:1.65;cursor:zoom-in;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;
}
.card.is-open .sum{display:block;overflow:visible;-webkit-line-clamp:unset;cursor:zoom-out}

.empty{text-align:center;padding:64px 20px 80px;color:var(--muted)}
.empty-icon{font-size:38px;line-height:1;opacity:.5}
.empty-q{margin:10px 0 4px;font-size:15px;color:var(--text-2)}
.empty-tip{margin:0;font-size:13px}

.foot{display:flex;gap:8px;flex-wrap:wrap;align-items:center;
  padding:22px 0 40px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}
.foot .dot{opacity:.6}

@media (max-width:760px){
  .wrap{width:calc(100% - 28px)}
  .topbar-inner{height:auto;padding:10px 0;flex-wrap:wrap;gap:10px}
  .tools{margin-left:0;width:100%}
  .search{flex:1}
  .search input{width:100%}
  .search kbd{display:none}
  .hero{padding:24px 0 4px}
  .stat{flex:1;min-width:0}
  .card{padding:14px 14px 13px}
  .card h3{font-size:16px}
}
@media print{
  .topbar,.tabs,.stats,a[href]::after{display:none}
  body{background:#fff}
}
</style>
</head>
<body>
<header class="topbar">
  <div class="wrap topbar-inner">
    <a class="brand" href="#top"><span class="logo">◆</span><span>行业资讯</span></a>
    <div class="tools">
      <label class="search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
        <input id="q" type="search" placeholder="搜索标题 / 摘要 / 来源" autocomplete="off" spellcheck="false" aria-label="搜索资讯">
        <kbd>/</kbd>
      </label>
      <select id="day" aria-label="选择日期"></select>
      <button id="theme" class="icon-btn" type="button" aria-label="切换深色模式"></button>
    </div>
  </div>
</header>

<main class="wrap" id="top">
  <section class="hero">
    <h1>多领域 · 行业资讯</h1>
    <p class="sub" id="sub"></p>
    <div class="stats">
      <span class="stat"><b id="stat-total">0</b><i>条资讯</i></span>
      <span class="stat"><b id="stat-src">0</b><i>个来源</i></span>
      <span class="stat stat-domains"><b id="stat-domains">—</b><i>个领域有更新</i></span>
    </div>
  </section>

  <div class="tabs" id="tabs" role="tablist" aria-label="领域筛选"></div>

  <div id="list" class="list"></div>
  <div id="empty" class="empty" hidden>
    <div class="empty-icon">◌</div>
    <p class="empty-q" id="empty-q">这一天还没有资讯</p>
    <p class="empty-tip">换个日期、领域或关键词试试</p>
  </div>
</main>

<footer class="wrap foot">
  <span>由 fetch_industry_news.py 自动生成</span><span class="dot">·</span>
  <span>内容版权归原站点所有</span><span class="dot">·</span>
  <span>数据仅保存在本机</span>
</footer>

<script>
const DATA = __NEWS_DATA__;
const DOMAINS = DATA.domains || [];
const DOMAIN_BY_KEY = {};
DOMAINS.forEach((d) => { DOMAIN_BY_KEY[d.key] = d; });

const $ = (sel, root = document) => root.querySelector(sel);
const listEl = $("#list");
const emptyEl = $("#empty");
const qEl = $("#q");
const dayEl = $("#day");
const tabsEl = $("#tabs");
const themeBtn = $("#theme");

const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
};

const state = { day: DATA.days && DATA.days[0] ? DATA.days[0].date : "", cat: "all", q: "" };

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));

function metaOf(key) {
  return DOMAIN_BY_KEY[key] || { key: key, label: key, short: key, light: "#3b5bdb", dark: "#7c9cff" };
}

function currentDay() {
  return (DATA.days || []).find((d) => d.date === state.day) || (DATA.days || [])[0];
}

function domainCounts(items) {
  const counts = {};
  items.forEach((it) => { counts[it.c] = (counts[it.c] || 0) + 1; });
  return counts;
}

function updateStats(items) {
  $("#stat-total").textContent = items.length;
  $("#stat-src").textContent = new Set(items.map((i) => i.s)).size;
  const active = DOMAINS.filter((d) => (items.some((it) => it.c === d.key))).length;
  $("#stat-domains").textContent = active + " / " + DOMAINS.length;
}

function buildTabs(items) {
  const counts = domainCounts(items);
  const tabs = ['<button class="tab" data-cat="all" type="button" aria-selected="false">全部<em>'
    + items.length + "</em></button>"];
  DOMAINS.forEach((d) => {
    const n = counts[d.key] || 0;
    if (!n) return;  // 当天没有内容的领域不占位
    tabs.push('<button class="tab" data-cat="' + esc(d.key) + '" type="button" aria-selected="false"'
      + ' style="--tab:' + esc(d.light) + '">' + esc(d.label) + "<em>" + n + "</em></button>");
  });
  tabsEl.innerHTML = tabs.join("");
  syncTabs();
}

function cardHtml(it) {
  const meta = metaOf(it.c);
  const time = it.p ? it.p.slice(11) : "";
  const title = it.l
    ? '<a href="' + esc(it.l) + '" target="_blank" rel="noopener noreferrer">' + esc(it.t) + "</a>"
    : esc(it.t);
  return '<article class="card" data-cat="' + esc(it.c) + '"'
    + ' style="--d-light:' + esc(meta.light) + ";--d-dark:" + esc(meta.dark) + '">'
    + '<div class="card-top"><span class="badge">' + esc(meta.short) + "</span>"
    + '<span class="src">' + esc(it.s) + "</span>"
    + (time ? '<span class="time">' + esc(time) + "</span>" : "")
    + "</div>"
    + "<h3>" + title + "</h3>"
    + (it.m ? '<p class="sum" title="点击展开 / 收起">' + esc(it.m) + "</p>" : "")
    + "</article>";
}

function render() {
  const d = currentDay();
  if (!d) { listEl.innerHTML = ""; emptyEl.hidden = false; return; }

  const counts = domainCounts(d.items);
  if (state.cat !== "all" && !counts[state.cat]) state.cat = "all";

  updateStats(d.items);
  buildTabs(d.items);

  const q = state.q.trim().toLowerCase();
  const items = d.items.filter((it) => {
    if (state.cat !== "all" && it.c !== state.cat) return false;
    if (!q) return true;
    return (it.t + " " + it.m + " " + it.s).toLowerCase().indexOf(q) !== -1;
  });

  const shown = domainCounts(items);
  let html = "";
  let last = null;
  items.forEach((it) => {
    if (state.cat === "all" && it.c !== last) {
      const meta = metaOf(it.c);
      html += '<div class="group" style="--d:' + esc(meta.light) + '">'
        + '<span class="gdot"></span>' + esc(meta.label)
        + '<span class="gcount">' + (shown[it.c] || 0) + " 条</span></div>";
      last = it.c;
    }
    html += cardHtml(it);
  });

  listEl.innerHTML = html;
  emptyEl.hidden = items.length > 0;
  $("#empty-q").textContent = q ? "没有找到包含“" + state.q.trim() + "”的资讯" : "这一天还没有资讯";
}

function syncTabs() {
  tabsEl.querySelectorAll(".tab").forEach((b) => {
    const on = b.dataset.cat === state.cat;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
}

tabsEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (!btn) return;
  state.cat = btn.dataset.cat;
  syncTabs();
  render();
});

dayEl.addEventListener("change", () => { state.day = dayEl.value; render(); });

let qTimer = 0;
qEl.addEventListener("input", () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { state.q = qEl.value; render(); }, 90);
});

document.addEventListener("keydown", (e) => {
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (e.key === "/" && tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") {
    e.preventDefault(); qEl.focus(); qEl.select();
  } else if (e.key === "Escape" && document.activeElement === qEl) {
    qEl.value = ""; state.q = ""; render(); qEl.blur();
  }
});

listEl.addEventListener("click", (e) => {
  const sum = e.target.closest(".sum");
  if (sum) sum.closest(".card").classList.toggle("is-open");
});

const ICON_SUN = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.2M12 19.8V22M2 12h2.2M19.8 12H22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M19.1 4.9l-1.6 1.6M6.5 17.5l-1.6 1.6"/></svg>';
const ICON_MOON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M20.6 14.4A8.6 8.6 0 0 1 9.6 3.4a8.5 8.5 0 1 0 11 11Z"/></svg>';

function applyTheme(theme, persist) {
  document.documentElement.dataset.theme = theme;
  themeBtn.innerHTML = theme === "dark" ? ICON_SUN : ICON_MOON;
  const label = theme === "dark" ? "切换到浅色模式" : "切换到深色模式";
  themeBtn.title = label;
  themeBtn.setAttribute("aria-label", label);
  if (persist) store.set("news-theme", theme);
}

themeBtn.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);
});

const mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
applyTheme(store.get("news-theme") || (mq && mq.matches ? "dark" : "light"), false);

if (mq) {
  const onChange = (e) => { if (!store.get("news-theme")) applyTheme(e.matches ? "dark" : "light", false); };
  if (mq.addEventListener) mq.addEventListener("change", onChange);
  else if (mq.addListener) mq.addListener(onChange);
}

(function init() {
  const params = new URLSearchParams(location.search);
  const forced = params.get("theme");
  if (forced === "dark" || forced === "light") applyTheme(forced, false);
  const forcedCat = params.get("cat");
  if (forcedCat === "all" || DOMAINS.some((d) => d.key === forcedCat)) state.cat = forcedCat;
  const forcedDay = params.get("day");
  if (forcedDay && (DATA.days || []).some((d) => d.date === forcedDay)) { state.day = forcedDay; }

  if (!DATA.days || !DATA.days.length) { emptyEl.hidden = false; return; }

  dayEl.innerHTML = DATA.days.map((d) =>
    '<option value="' + esc(d.date) + '">' + esc(d.date) + " · " + d.count + " 条</option>"
  ).join("");

  $("#sub").textContent = DATA.days.length + " 天归档 · 更新于 " + DATA.generated + " · 按 / 快速搜索";

  syncTabs();
  render();
})();
</script>
</body>
</html>
"""


def _html_items(rows: list[dict]) -> list[dict]:
    ordered = sorted(rows, key=_sort_key)
    return [{
        "c": r["domain"],
        "s": r["source"],
        "t": r["title"],
        "m": r["summary"],
        "l": r["link"],
        "p": r["published"].strftime("%Y-%m-%d %H:%M") if r["published"] else "",
    } for r in ordered]


def gather_days(output_dir: Path, current_day: str, current_rows: list[dict],
                limit: int) -> list[dict]:
    """收集输出目录里所有日期的数据，最近 limit 天。"""

    days: dict[str, list[dict]] = {current_day: current_rows}
    for path in output_dir.glob("*_news.csv"):
        day_part = path.name.split("_")[0]
        try:
            datetime.strptime(day_part, "%Y-%m-%d")
        except ValueError:
            continue
        if day_part not in days:
            days[day_part] = read_existing(path)

    ordered = sorted(days.items(), key=lambda kv: kv[0], reverse=True)[:max(limit, 1)]
    payload: list[dict] = []
    for day_part, rows in ordered:
        items = _html_items(rows)
        payload.append({
            "date": day_part,
            "count": len(items),
            "sources": len({item["s"] for item in items}),
            "items": items,
        })
    return payload


def build_html(html_path: Path, days: list[dict], generated: datetime) -> None:
    """生成自包含网页：数据以 JSON 内嵌，file:// 直接打开即可，无跨域问题。"""

    domains = [{"key": key, **DOMAIN_META[key]} for key in DOMAIN_ORDER]
    data = json.dumps(
        {"generated": generated.strftime("%Y-%m-%d %H:%M"),
         "domains": domains, "days": days},
        ensure_ascii=False, separators=(",", ":"),
    ).replace("</", "<\\/")

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(HTML_TEMPLATE.replace("__NEWS_DATA__", data), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="抓取 AI / 嵌入式 / 汽车 / 机器人 / 医疗 / 前沿六领域行业资讯",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="结果保存目录")
    parser.add_argument("--date", help="归档日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--days", type=int, default=3,
                        help="只保留最近 N 天发布的条目")
    parser.add_argument("--max-per-feed", type=int, default=15,
                        help="每个源最多保留条数")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次请求超时（秒）")
    parser.add_argument("--retries", type=int, default=1, help="失败重试次数")
    parser.add_argument("--workers", type=int, default=8, help="并发线程数")
    parser.add_argument("--no-merge", action="store_true", help="不合并当天已有文件，直接覆盖")
    parser.add_argument("--no-txt", action="store_true", help="只生成 CSV")
    parser.add_argument("--no-md", action="store_true", help="不生成 Markdown")
    parser.add_argument("--no-html", action="store_true", help="不生成 / 不更新 index.html")
    parser.add_argument("--html", type=Path, default=None,
                        help="index.html 路径（默认放在输出目录的上一级）")
    parser.add_argument("--html-days", type=int, default=10,
                        help="网页中保留最近多少天的数据")
    parser.add_argument("--no-log", action="store_true", help="不写日志文件")
    parser.add_argument("--no-seen-index", action="store_true",
                        help="关闭跨天去重（允许同一篇文章在连续几天重复出现）")
    parser.add_argument("--list-sources", action="store_true", help="列出所有资讯源后退出")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    return parser


def setup_logging(output_dir: Path, day: str, verbose: bool, write_file: bool) -> None:
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOG.handlers.clear()
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    LOG.addHandler(console)
    if write_file:
        log_dir = output_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / f"fetch_{day}.log", encoding="utf-8", mode="a"
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        LOG.addHandler(file_handler)


# ---------------------------------------------------------------
# 跨天去重索引：同一个链接只进最近一次抓取的那天，避免列表页滚动重复
# ---------------------------------------------------------------

SEEN_FILENAME = ".seen_urls.json"
SEEN_TTL_DAYS = 120


def load_seen_index(output_dir: Path) -> dict[str, str]:
    path = output_dir / SEEN_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        LOG.warning("跨天去重索引损坏，已重建：%s", path)
        return {}
    return data if isinstance(data, dict) else {}


def save_seen_index(output_dir: Path, seen: dict[str, str], today: str) -> None:
    cutoff = (datetime.strptime(today, "%Y-%m-%d")
              - timedelta(days=SEEN_TTL_DAYS)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in seen.items() if isinstance(v, str) and v >= cutoff}
    if len(pruned) > 20000:  # 兜底：最多保留 2 万条
        pruned = dict(sorted(pruned.items(), key=lambda kv: kv[1], reverse=True)[:20000])
    path = output_dir / SEEN_FILENAME
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pruned, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    setup_console()

    if args.list_sources:
        print(f"{'领域':<14}{'类型':<6}{'源':<22}URL")
        for src in SOURCES:
            print(f"{domain_label(src.domain):<14}{src.kind:<6}{src.name:<22}{src.url}")
        print(f"\n共 {len(SOURCES)} 个源，覆盖 {len(DOMAIN_ORDER)} 个领域")
        return 0

    now = local_now()
    if args.date:
        try:
            day = datetime.strptime(args.date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            print(f"日期格式错误：{args.date}，应为 YYYY-MM-DD", file=sys.stderr)
            return 2
    else:
        day = now.strftime("%Y-%m-%d")

    output_dir: Path = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(output_dir, day, args.verbose, not args.no_log)

    cutoff = now - timedelta(days=max(args.days, 1))
    LOG.info("开始抓取 %d 个资讯源（最近 %d 天，截止 %s）",
             len(SOURCES), args.days, cutoff.strftime("%Y-%m-%d %H:%M"))

    results: list[FetchResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                fetch_source, src,
                timeout=args.timeout, days=args.days,
                max_items=args.max_per_feed, cutoff=cutoff, retries=args.retries,
            ): src
            for src in SOURCES
        }
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001
                result = FetchResult(source=src, error=f"{type(exc).__name__}: {exc}")
            results.append(result)
            if result.ok:
                LOG.info("[OK]   %-20s %2d 条 (源内共 %d, %.1fs)",
                         src.name, len(result.items), result.total, result.elapsed)
            else:
                LOG.warning("[FAIL] %-20s %s", src.name, result.error)

    ok_count = sum(1 for r in results if r.ok)
    new_rows = collect(results)
    LOG.info("抓取完成：%d/%d 个源成功，去重后 %d 条", ok_count, len(SOURCES), len(new_rows))

    if ok_count == 0:
        LOG.error("所有资讯源均抓取失败，请检查网络或代理设置")
        return 1

    # 跨天去重：已经收录过的链接不再进今天的文件（列表页会长期挂着旧文章）
    seen_index = {} if args.no_seen_index else load_seen_index(output_dir)
    if seen_index:
        before = len(new_rows)
        new_rows = [r for r in new_rows if dedupe_key(r) not in seen_index]
        if before != len(new_rows):
            LOG.info("跳过 %d 条此前已收录的旧条目", before - len(new_rows))

    csv_path = output_dir / f"{day}_news.csv"
    txt_path = output_dir / f"{day}_news.txt"
    md_path = output_dir / f"{day}_news.md"
    html_path = (args.html.expanduser().resolve() if args.html
                 else output_dir.parent / "index.html")

    if args.no_merge or not csv_path.exists():
        rows = new_rows
    else:
        rows = merge_rows(read_existing(csv_path), new_rows)

    write_csv(rows, csv_path, day)

    failed = [r for r in results if not r.ok]
    grouped = _by_domain(rows)
    stats = [
        f"本次运行 : 成功 {ok_count}/{len(SOURCES)} 个源，新增 {len(new_rows)} 条，"
        f"合并后共 {len(rows)} 条",
        f"领域分布 : {_domain_summary(grouped)}",
        f"失败源   : {', '.join(r.source.name for r in failed) if failed else '无'}",
    ]
    if not args.no_txt:
        write_txt(rows, txt_path, day, stats)
    if not args.no_md:
        write_markdown(rows, md_path, day, stats)

    if not args.no_html:
        try:
            archive = gather_days(output_dir, day, rows, args.html_days)
            build_html(html_path, archive, now)
            LOG.info("网页已更新：%s（%d 天）", html_path, len(archive))
        except OSError as exc:
            LOG.warning("生成网页失败：%s", exc)

    if not args.no_seen_index:
        for row in new_rows:
            seen_index.setdefault(dedupe_key(row), day)
        save_seen_index(output_dir, seen_index, day)

    print("")
    print("=" * 60)
    print(f"  日期     : {day}")
    print(f"  新增     : {len(new_rows)} 条")
    print(f"  文件总数 : {len(rows)} 条")
    print(f"  领域分布 : {_domain_summary(grouped)}")
    print(f"  CSV      : {csv_path}")
    if not args.no_txt:
        print(f"  TXT      : {txt_path}")
    if not args.no_md:
        print(f"  MD       : {md_path}")
    if not args.no_html:
        print(f"  网页     : {html_path}")
    print("=" * 60)

    for result in sorted(results, key=lambda r: (not r.ok, DOMAIN_ORDER.index(r.source.domain)
                                                 if r.source.domain in DOMAIN_ORDER else 99,
                                                 r.source.name)):
        if result.ok:
            print(f"  {domain_label(result.source.domain):<14} {result.source.name:<20} "
                  f"{len(result.items):>3} 条")
    if failed:
        print("\n  以下源本次失败（不影响其他源）：")
        for result in failed:
            print(f"  - {result.source.name}: {result.error}")

    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
