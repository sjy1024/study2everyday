# 多领域行业资讯日报 · 使用说明

> 这是一个装在自己电脑上的小工具：每天自动去 30 多个网站抓行业新闻，
> 汇总成一个可以双击打开的网页，外加 CSV / TXT / Markdown 三种表格文件。
>
> 覆盖 6 个领域：**人工智能、嵌入式/硬件、汽车/智能网联、机器人/具身智能、医疗科技、世界模型/端侧 AI**

---

## 一、你拿到的文件夹

```
任意文件夹\                     ← 整个目录可以放在任何位置（含中文、空格都行）
├─ 运行.bat                     ← 双击这个：抓取 + 更新网页
├─ index.html                   ← 双击这个：看资讯（每次抓取后自动重建）
├─ readme2user.md               ← 本文件
├─ worknews\                    ← 抓到的数据（首次运行自动创建）
└─ Demo\                        ← 程序本体
    ├─ fetch_industry_news.py      抓取脚本
    ├─ rebuild_html.py             只重建网页，不联网
    └─ README.md                   进阶说明（改抓取规则看这个）
```

> 如果收到的压缩包里带着别人的示例数据（`worknews\` 里的 csv、`index.html`），
> 想从空白开始就按第六节「清空示例数据」处理。

---

## 二、第一次使用（3 步）

### 第 1 步：装 Python

1. 到 <https://www.python.org/downloads/> 下载 **Python 3.8 或更新版本**；
2. 安装时**务必勾选** 底部的 `Add Python to PATH`；
3. 验证：按 `Win + R` → 输入 `cmd` → 回车 → 输入 `python --version`，能看到版本号即可。

### 第 2 步：装唯一的依赖

在文件夹里 **Shift + 右键 → 「在此处打开 PowerShell 窗口」**，执行：

```powershell
pip install requests
```

> 只有 `requests` 一个第三方库。装一次就行，以后不用再装。

### 第 3 步：双击 `运行.bat`

- 会弹出一个黑窗口，显示抓取进度，通常 **1～2 分钟**；
- 结束时显示「新增多少条 / 各领域分布 / 成功几个源」；
- 按任意键关闭，然后**双击 `index.html`** 就能看了。

抓取需要能上外网；公司网络如果拦了某些站点，对应条目会少，不影响其它源。

---

## 三、每天自动跑（可选）

想让它每天固定时间自己跑，在文件夹里打开 PowerShell 执行下面这段：

```powershell
$root = (Get-Location).Path
$py   = (Get-Command python).Source          # 若用 Anaconda，换成它的 python.exe 路径
$act  = New-ScheduledTaskAction -Execute $py `
        -Argument "`"$root\Demo\fetch_industry_news.py`" --days 3" `
        -WorkingDirectory "$root\Demo"
$trg  = New-ScheduledTaskTrigger -Daily -At 09:30
Register-ScheduledTask -TaskName "DailyNews" -Action $act -Trigger $trg -Force
```

改时间就改 `-At 09:30` 后重跑一遍；取消自动运行：

```powershell
Unregister-ScheduledTask -TaskName "DailyNews" -Confirm:$false
```

**注意**：这是本机定时任务，只有「电脑开机 + 已登录你的账号」时才会执行；
关机、休眠、未登录都会跳过当天，而且**不会补跑**。

---

## 四、网页怎么用

| 功能 | 操作 |
| --- | --- |
| 切换领域 | 顶部标签：全部 / 人工智能 / 嵌入式 / 汽车 / 机器人 / 医疗 / 前沿 |
| 换日期 | 右上角日期下拉，保留最近 10 天 |
| 搜索 | 直接点搜索框输入，或按 `/` 聚焦、`Esc` 清空 |
| 深色模式 | 右上角 ☀/☾ 切换，会记住你的选择 |
| 看原文 | 点标题，在新标签页打开原网站 |
| 展开摘要 | 摘要默认 3 行，点一下展开全文 |

网页是**本地文件**（数据已经打包进 HTML 里），不需要服务器、不联网也能看，直接双击即可。

---

## 五、文件说明

| 位置 | 说明 |
| --- | --- |
| `index.html` | 资讯网页，每次抓取后整份重建；手动改它没意义，下次会被覆盖 |
| `worknews\YYYY-MM-DD_news.csv` | 当天全部条目，Excel 可直接打开（列：日期/领域/来源/标题/摘要/链接/发布时间） |
| `worknews\YYYY-MM-DD_news.txt` | 同上，纯文本，适合打印或存档 |
| `worknews\YYYY-MM-DD_news.md` | 同上，Markdown，适合贴到笔记软件 |
| `worknews\logs\` | 运行日志，抓取失败时先看这里 |
| `worknews\.seen_urls.json` | 跨天去重记录，**别手动改**，删了会导致旧文章重复出现 |

---

## 六、常见问题

**Q：双击 `运行.bat` 提示「没有找到 Python」**
没装 Python，或安装时没勾 `Add Python to PATH`。重装并勾选；也可以用记事本打开 `运行.bat`，
把 `D:\soft\Anaconda3\python.exe` 那一行改成你自己的 `python.exe` 路径。

**Q：报 `ModuleNotFoundError: No module named 'requests'`**
执行 `pip install requests`。如果提示 pip 不存在，用 `python -m pip install requests`。

**Q：窗口一闪就没了**
正常情况下会停在「按任意键关闭窗口」。如果真闪退，多半是 Python 路径有问题，
用 PowerShell 手动跑一次看报错：`python Demo\fetch_industry_news.py`。

**Q：抓到的条数很少，或者某个网站没有**
单个源失败是常态（反爬、临时故障、网站改版），不影响其它源；窗口末尾会列出「本次失败的源」。
如果连续多天都是 0 条，先检查网络 / 代理。

**Q：网页打开还是旧内容**
说明还没抓新的：双击 `运行.bat` 跑一次。若只是想让网页按现有 CSV 重新生成（不联网），执行：
`python Demo\rebuild_html.py`。

**Q：摘要空白、时间显示「未知」**
部分中文网站没有 RSS，只能从列表页拿到标题和链接，没有摘要和时间，属正常现象。

**Q：想清空示例数据，从空白开始**
删除 `worknews\` 里所有 `*_news.csv`、`*_news.txt`、`*_news.md`、`.seen_urls.json` 和 `logs\`，
再删掉 `index.html`，然后双击 `运行.bat` 即可重建。

**Q：想加网站、改领域、调关键词**
那不属于「使用」范畴了，看 `Demo\README.md` 的「维护资讯源」一节，有 RSS 和列表页两种配置模板。

---

## 七、说明与边界

- **数据只保存在本机**，不上传任何服务器，也不收集使用信息；
- 抓取的是各网站公开的 RSS 订阅和新闻列表页，**版权归原网站所有**，
  仅供个人学习和行业跟踪，请勿用于商业转载；
- 抓取频率很低（每天 1 次），但仍建议不要改小了频次去压站；
- 源站改版会导致个别站点抓不到，属于长期使用中的正常维护成本；
- 只在 Windows 上验证过（Windows 10/11 + Python 3.8+）。Linux/macOS 下
  `python Demo/fetch_industry_news.py` 本身也能跑，只是 `.bat` 用不上。

---

## 八、命令备忘

```powershell
# 抓取 + 更新网页（等于双击 运行.bat）
python Demo\fetch_industry_news.py

# 抓最近 7 天（默认 3 天）
python Demo\fetch_industry_news.py --days 7

# 只重建网页，不联网
python Demo\rebuild_html.py

# 查看内置的 33 个资讯源
python Demo\fetch_industry_news.py --list-sources
```
