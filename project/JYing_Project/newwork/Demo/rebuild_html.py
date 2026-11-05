#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只重建 index.html，不联网抓取
=============================

读取输出目录里已有的 `YYYY-MM-DD_news.csv`，重新生成自包含的 index.html。
适合"抓取失败/不想联网，只想刷新页面"或改了模板之后重出页面。

用法
----
    python rebuild_html.py                    # 默认 worknews → ..\\index.html
    python rebuild_html.py --html-days 30     # 网页保留最近 30 天
    python rebuild_html.py --html D:\\tmp\\news.html

依赖同目录下的 fetch_industry_news.py，不访问网络。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fetch_industry_news as news


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用已有 CSV 重新生成资讯网页 index.html",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--output-dir", type=Path, default=news.DEFAULT_OUTPUT_DIR,
                        help="CSV 所在目录")
    parser.add_argument("--html", type=Path, default=None,
                        help="网页输出路径（默认 <输出目录>/../index.html）")
    parser.add_argument("--html-days", type=int, default=10,
                        help="网页里保留最近多少天的数据")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    news.setup_console()

    output_dir: Path = args.output_dir.expanduser().resolve()
    if not output_dir.is_dir():
        print(f"目录不存在：{output_dir}", file=sys.stderr)
        return 2

    csv_files = sorted(output_dir.glob("*_news.csv"), reverse=True)
    if not csv_files:
        print(f"{output_dir} 里没有 *_news.csv，先运行 fetch_industry_news.py", file=sys.stderr)
        return 1

    latest = csv_files[0]
    day = latest.name.split("_")[0]
    rows = news.read_existing(latest)
    days = news.gather_days(output_dir, day, rows, args.html_days)

    html_path = (args.html.expanduser().resolve() if args.html
                 else output_dir.parent / "index.html")
    news.build_html(html_path, days, news.local_now())

    total = sum(d["count"] for d in days)
    print(f"已生成 {html_path}")
    print(f"  日期范围 : {days[-1]['date']} ~ {days[0]['date']}（{len(days)} 天）")
    print(f"  条目总数 : {total} 条（含各天归档，最新一天 {days[0]['count']} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
