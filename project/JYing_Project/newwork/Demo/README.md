# 多领域行业资讯每日抓取

`fetch_industry_news.py` 每天抓取 **6 个领域**的行业资讯：

| 领域 | 关键内容 |
| --- | --- |
| 人工智能 | 大模型、Agent、AI 芯片、算力 |
| 嵌入式 / 硬件 | MCU、开发板、EDA、半导体、IoT |
| 汽车 / 智能网联 | 智驾、座舱、新能源、车企动态 |
| 机器人 / 具身智能 | 人形机器人、灵巧手、具身模型 |
| 医疗科技 | 医疗器械、手术机器人、脑机接口、FDA/NMPA |
| 世界模型 / 端侧 AI | World Model、TinyML、边缘推理 |

结果按日期归档为 **CSV + TXT + Markdown**，并生成一个**双击即可查看的网页**：

```
D:\AI\DSHworkspace\newwork\worknews\2026-11-04_news.csv
D:\AI\DSHworkspace\newwork\worknews\2026-11-04_news.txt
D:\AI\DSHworkspace\newwork\worknews\2026-11-04_news.md
D:\AI\DSHworkspace\newwork\worknews\logs\fetch_2026-11-04.log
D:\AI\DSHworkspace\newwork\index.html          ← 双击打开就能看
```

---

## 1. 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.8+（本机 Anaconda `D:\soft\Anaconda3\python.exe`，3.10.9） |
| 依赖 | `requests`（本机已装；缺失时 `pip install requests`） |

只用 `requests` + 标准库（`xml.etree` 解析 RSS、`re` 解析 HTML 列表页），
**不需要** feedparser、bs4、lxml。

## 2. 运行

> 日常使用不必敲命令：双击项目根目录的 **`运行.bat`** 即可（抓取 + 更新网页 + 显示汇总）。
> 该 bat 固定使用本机 Anaconda 的 python，保存为 ANSI(GBK) 编码以适配中文控制台。

```powershell
cd D:\AI\DSHworkspace\newwork\Demo
python fetch_industry_news.py                 # 抓取最近 3 天，保存为今天的文件
python fetch_industry_news.py --days 7        # 放宽到最近 7 天（仅对 RSS 源生效）
python fetch_industry_news.py --list-sources  # 查看 33 个源及所属领域
python fetch_industry_news.py --date 2026-11-04 --days 1   # 指定归档日期
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--output-dir` | `D:\AI\DSHworkspace\newwork\worknews` | 输出目录（也可用环境变量 `NEWS_OUTPUT_DIR`） |
| `--date` | 今天 | 归档日期 `YYYY-MM-DD` |
| `--days` | 3 | 只保留最近 N 天发布的条目（HTML 列表页不受此限制） |
| `--max-per-feed` | 15 | 每个源最多保留条数 |
| `--timeout` | 15 | 单次请求超时（秒） |
| `--retries` | 1 | 失败重试次数 |
| `--workers` | 8 | 并发线程数 |
| `--no-merge` | 关 | 不合并当天已有数据，直接覆盖 |
| `--no-txt` / `--no-md` | 关 | 不生成 TXT / 不生成 Markdown |
| `--no-html` | 关 | 不更新 `index.html` |
| `--html` | `<输出目录>/../index.html` | 网页输出路径 |
| `--html-days` | 10 | 网页里保留最近多少天的数据 |
| `--no-seen-index` | 关 | 关闭跨天去重 |
| `--no-log` | 关 | 不写日志 |

退出码：`0` 成功；`1` 所有源都失败或无数据；`2` 参数错误。

**同一天重复运行是安全的**：会与已有 CSV 按链接去重合并，只追加新内容。

**跨天去重**：`worknews\.seen_urls.json` 记录已收录的链接，同一篇文章只会进第一次抓到它的那天，
避免列表页长期挂着旧文章导致天天重复。想恢复"每天都是最近 3 天快照"的旧行为，加 `--no-seen-index`。

## 3. 输出格式

| 文件 | 内容 |
| --- | --- |
| `*.csv` | UTF-8 BOM，列：`日期, 领域, 来源, 标题, 摘要, 链接, 发布时间`，Excel 双击不乱码 |
| `*.txt` | 按六个领域分节，带序号、来源、时间、摘要、原文链接 |
| `*.md` | 同上，标题为链接、摘要用引用块，方便贴笔记 |
| `index.html` | 自包含网页（详见第 4 节） |

## 4. 网页 index.html（双击即看）

每次运行都会重新生成，数据以 JSON **内嵌**在 HTML 里，所以双击打开即可，
不需要服务器，也不受 `file://` 下 `fetch()` 读本地文件的限制。

* **6 个领域标签**：按当天有内容的领域自动生成，带条数，各自独立配色
* **深色 / 浅色模式**：默认跟随系统，右上角切换并记忆；`?theme=dark` 可强制
* **日期下拉**：最近 10 天归档（`--html-days` 可调）
* **实时搜索**：按 `/` 聚焦，`Esc` 清空
* **摘要展开**：默认 3 行，点击展开；标题跳原文
* URL 参数：`?theme=dark`、`?cat=auto`（ai / embedded / auto / robot / medical / frontier）、`?day=2026-11-04`

> 页面是**生成时快照**，不实时读文件。只想刷新页面不重新抓取时：
> `cd Demo; python rebuild_html.py`

## 5. 分类规则

* **垂直源**（量子位、Hackaday、OFweek 医械、具身之家等）全量收录，直接归入所属领域；
* **综合源**（36氪、IT之家、极客公园、The Verge、Tom's Hardware）先按
  六套中英文关键词打分，命中最多者即为领域；一个都没命中则丢弃，避免灌入无关社会新闻；

关键词表在脚本 `KEYWORDS` 里，按需增删。

## 6. 资讯源清单（33 个）

| 领域 | 源 | 方式 |
| --- | --- | --- |
| 人工智能 | 量子位、OpenAI、Google AI、Google DeepMind、Microsoft Research、BAIR、MarkTechPost | RSS |
| 人工智能 | 36氪、极客公园、钛媒体、InfoQ 中文、雷峰网、IT之家、The Verge | RSS + 关键词归类 |
| 嵌入式/硬件 | CNX Software、Hackaday、Embedded.com、EE Journal、Adafruit、Semiconductor Digest、DIGITIMES、EE Times | RSS |
| 嵌入式/硬件 | 21ic 电子网、电子发烧友 | 列表页 |
| 汽车/智能网联 | 第一电动网、盖世汽车 | 列表页 |
| 机器人/具身智能 | 具身之家 | 列表页 |
| 医疗科技 | OFweek 医械、Medical Economics（med-tech 专题） | 列表页 |
| 世界模型/端侧AI | Edge AI & Vision、RT Insights | RSS |
| 世界模型/端侧AI | Edge AI Foundation | 列表页 |
| 综合兜底 | Tom's Hardware | RSS + 关键词归类 |

**未接入**（探测后放弃）：EEWorld（连接被重置）、The Robot Report（403 Cloudflare）、
亿欧/沙利文（报告类，改为看原文/周更）、车云网（纯 JS 渲染）、器械之家（超时）、
CNX 中文站（域名未确认）。详见 `..\需求\需求分析与改动清单.md`。

## 7. 每天 09:30 自动运行（已配置）

| 项目 | 值 |
| --- | --- |
| 任务名 | `AI_Embedded_DailyNews` |
| 触发 | 每天 09:30 |
| 执行 | `D:\soft\Anaconda3\python.exe "…\Demo\fetch_industry_news.py" --days 3` |
| 工作目录 | `D:\AI\DSHworkspace\newwork\Demo` |
| 运行身份 | 当前用户，仅在该用户登录时运行 |
| 错过策略 | 不补跑（关机/休眠则当天跳过） |

```powershell
Get-ScheduledTaskInfo -TaskName "AI_Embedded_DailyNews"   # 下次运行时间、上次结果
Start-ScheduledTask -TaskName "AI_Embedded_DailyNews"     # 立刻跑一次
Unregister-ScheduledTask -TaskName "AI_Embedded_DailyNews" -Confirm:$false
```

> 关机时不会运行——任务计划程序是本地调度器。要"关机也跑"需改用 GitHub Actions / 云服务器。

## 8. 维护资讯源

### 加一个 RSS 源

```python
Source("站点名", "https://example.com/feed", "ai"),          # 垂直源：全量收录
Source("站点名", "https://example.com/feed", "ai", strict=False),  # 综合源：关键词归类
```

### 加一个没有 RSS 的站点（列表页）

```python
Source("站点名", "https://example.com/news/", "embedded", kind="html",
       item_re=r'href="(/news/\d+\.html)"',   # ① 文章链接
       title_re=r'>([^<>]{10,120})<',          # ② 标题（一般不用改）
       date_re=r'(20\d{2}-\d{2}-\d{2})'),      # ③ 时间，可留空
```

调试时先 `python -c "import fetch_industry_news as f; ..."` 或直接 `--list-sources` 看配置。
标题提取顺序：`title` 属性 → 标签内文本 → `alt` 属性；时间取链接前后 600/900 字符窗口内的第一处匹配。
`date_re` 匹配不到时该条只显示"未知时间"，不会丢。

### 已知限制

- 列表页通常**没有摘要**，这些条目的「摘要」为空；
- 部分站点只给"年-月"（如 OFweek），时间显示为「未知」；
- 少数站点会封 IP（CNX Software 目前返回 403），脚本会标记 `[FAIL]` 并继续跑其他源；
- 网页体积随天数增长（10 天约 800 KB），本地打开无压力。

## 9. 只重建网页

`rebuild_html.py` 读取已有 CSV，重新生成 `index.html`，不联网：

```powershell
cd D:\AI\DSHworkspace\newwork\Demo
python rebuild_html.py                 # 默认 worknews → ..\index.html
python rebuild_html.py --html-days 30  # 网页保留 30 天
```

## 10. 排错

| 现象 | 处理 |
| --- | --- |
| 个别源 `[FAIL] HTTP 403` | 站点反爬/封 IP，稍后重试或删掉该源 |
| 某源 0 条 | 该源最近 `--days` 天没有新文章，或列表页结构变了（改 `item_re`） |
| 列表页抓到导航链接 | `item_re` 太宽，收紧正则（例如要求 `/news/\d+`） |
| 全部失败 | 检查网络/代理，`requests` 会读 `HTTP_PROXY`、`HTTPS_PROXY` |
| Excel 乱码 | CSV 已带 UTF-8 BOM；老版本 Excel 用「数据→从文本」导入选 UTF-8 |
| 网页没更新 | 看是否加了 `--no-html`；或手动 `python rebuild_html.py` |
| 想清空重来 | 删 `YYYY-MM-DD_news.csv` 与 `.seen_urls.json` 后重跑 |

## 11. 免责声明

内容版权归原站点所有，仅用于个人学习与行业跟踪；请遵守各站 robots.txt 与转载规定，
控制抓取频率，不要用于商业再分发。
