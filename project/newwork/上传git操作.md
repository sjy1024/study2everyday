

## Python 项目上传 GitHub 操作指南

---

## 一、准备工作

### 1. 确认项目内容

你的项目包含：

| 文件名 | 说明 | 是否上传 |
| --- | --- | --- |
| `fetch_industry_news.py` | 主脚本 | ✅ |
| `rebuild_html.py` | 重建网页脚本 | ✅ |
| `运行.bat` | 运行脚本 | ✅ |
| `readme2user.md` | 用户说明 | ✅ |
| `Demo/` 目录 | 程序本体 | ✅ |
| `worknews/` 目录 | **数据文件** ❌ | ❌ |
| `worknews/logs/` | 日志 | ❌ |
| `worknews/.seen_urls.json` | 去重记录 | ❌ |
| `index.html` | 生成的网页 | ❌ |

> `worknews/` 目录是**每次抓取生成的实时数据**，不应该上传到 Git。

### 2. 创建 .gitignore

新建 `项目目录/.gitignore`，内容：

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# 虚拟环境
.env
.venv/
venv/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# 数据（不要上传）
worknews/
index.html
*.log

# Windows
Thumbs.db
desktop.ini

# 临时文件
*.tmp
```

保存后，`git status` 不会再显示这些文件。

---

## 二、上传步骤（分两种场景）

### 场景 A：GitHub 仓库已存在（如你提供的 https://github.com/sjy1024/study2everyday）

#### 1. 在 GitHub 网页先创建好仓库

1. 打开 `https://github.com/sjy1024/study2everyday`
2. 找到 `project/` 目录，看看里面是否有内容
   - 如果**有内容**：后续操作会用 `--force` 或手动处理冲突
   - 如果**空**：直接按下面的步骤走

#### 2. 在本地配置 Git（第一次需要）

```powershell
# 设置用户名和邮箱（用 GitHub 的，不是 GitCode 的）
git config --global user.name "YourGitHubName"
git config --global user.email "youremail@example.com"

# 配置密码/Token
# 如果 Git 提示无法访问 GitHub，需要用 GitHub Token 或 SSH
```

#### 3. 克隆仓库到本地（如果没有本地副本）

```powershell
# 选择克隆到本地某个地方
git clone https://github.com/sjy1024/study2everyday.git D:\temp\study2everyday
cd D:\temp\study2everyday
```

> 如果你已有本地副本（如 `D:\AI\DSHworkspace\newwork`），跳到第 4 步。

#### 4. 将项目文件放入 project/ 目录

```powershell
# 进入项目根目录
cd D:\temp\study2everyday

# 新建 project 目录（如果不存在）
if (!(Test-Path project)) { New-Item -ItemType Directory -Name project }

# 复制项目文件到 project 目录
Copy-Item "D:\AI\DSHworkspace\newwork\Demo" -Destination "project\" -Recurse
Copy-Item "D:\AI\DSHworkspace\newwork\运行.bat" -Destination "project\"
Copy-Item "D:\AI\DSHworkspace\newwork\readme2user.md" -Destination "project\"
Copy-Item "D:\AI\DSHworkspace\newwork\.gitignore" -Destination "project\"
```

> `worknews/`、`index.html` 等数据文件**不要复制**。

#### 5. 初始化并添加所有文件

```powershell
cd project

# 查看状态
git status

# 添加所有文件
git add .

# 提交
git commit -m "Add: 多领域行业资讯抓取工具"
```

#### 6. 推送到 GitHub

```powershell
# 确保在 main 分支（或其他目标分支）
git checkout main

# 推送到远程
git push origin main
```

> 首次推送可能需要输入 GitHub 用户名和密码（如果用 Token 则输入 Token）。

---

### 场景 B：手动操作（不克隆整个仓库）

如果不想克隆整个 `study2everyday` 仓库，可以直接对当前项目目录操作：

```powershell
# 1. 进入项目目录
cd D:\AI\DSHworkspace\newwork

# 2. 初始化 Git 仓库
git init

# 3. 创建 .gitignore（按上面的内容）
# 这一步已经帮你创建好了 .gitignore

# 4. 添加所有需要上传的文件
git add fetch_industry_news.py README.md .gitignore
git add README.md

# 5. 提交
git commit -m "Add: 多领域行业资讯抓取工具 v1"
```

#### 添加远程仓库

```powershell
# 添加远程（注意用 SSH 或 HTTPS+Token）
git remote add origin git@github.com:sjy1024/study2everyday.git

# 推送（如果已有 content 需处理冲突）
git push -u origin main
```

---

## 三、如果没有 GitHub 权限（无法 push）

如果你的账户没有权限直接写 `sjy1024/study2everyday`，有两种选择：

### 方案 1：Fork 你自己的仓库

1. 在 GitHub 上 Fork 一个同名仓库（或创建新仓库）
2. 用你的 Fork 地址替换上面的 `origin`

### 方案 2：用 Pull Request

1. 先 Fork 该仓库到你的账户
2. 在你的 Fork 里操作上面的步骤
3. 发起 Pull Request 到原仓库

---

## 四、如果已有文件需要覆盖

执行 `git push` 时如果发现远程有同名文件会提示冲突：

```
To github.com:sjy1024/study2everyday.git
 ! [rejected]        main -> main (fetch first)
```

解决方法：

```powershell
# 方法 1：先拉取远程再合并
git pull origin main
# 解决冲突后再次 push
git add . && git commit -m "Merge"
git push

# 方法 2：强制推送（谨慎使用！）
git push --force origin main
```

> **强制推送会覆盖远程的分支**，确保你确定要这样做！

---

## 五、如果用 Token 代替密码

Windows 上不需要额外配置，GitHub CLI 可以帮你管理。如果不行，手动配置：

#### 1. 生成 GitHub Personal Access Token

1. 打开 `https://github.com/settings/tokens`
2. 点击 "Generate new token (classic)"
3. 勾选 `repo` 权限
4. 生成 Token 并复制

#### 2. 上传时用 Token

```powershell
# 推送时输入 Token 而不是密码
git push -u origin main
```

或使用 SSH（推荐）：

```powershell
# 生成 SSH 密钥
ssh-keygen -t ed25519 -C "your-email@example.com"

# 复制公钥到剪贴板
clip < $env:USERPROFILE\.ssh\id_ed25519.pub

# 将公钥添加到 GitHub：Settings → SSH and GPG keys

# 使用 SSH 地址
git remote set-url origin git@github.com:sjy1024/study2everyday.git
git push origin main
```

---

## 六、快速操作脚本（Windows PowerShell）

复制到你本地仓库根目录运行：

```powershell
# newwork_to_git.ps1
# 将 newwork 项目上传到 study2everyday/project

$projectRoot = "D:\AI\DSHworkspace\newwork"
$gitRepoRoot = "$env:TEMP\study2everyday"  # 临时仓库

# 1. Clone 或创建局部 Git
if (!(Test-Path "$gitRepoRoot\.git")) {
    git clone https://github.com/sjy1024/study2everyday.git "$gitRepoRoot"
}
cd "$gitRepoRoot"

# 2. 同步文件
if (Test-Path "$projectRoot\Demo") {
    Remove-Item "project\*" -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item "$projectRoot\Demo" "project\" -Recurse
    Copy-Item "$projectRoot\运行.bat" "project\"
    Copy-Item "$projectRoot\readme2user.md" "project\"
    Copy-Item "$projectRoot\.gitignore" "project\"
}

# 3. Commit 和 Push
git add project
git commit -m "Add: 多领域行业资讯抓取工具"
git push origin main
```

---

## 七、遇到问题？

| 问题 | 解决方法 |
| --- | --- |
| `git: command not found` | Git 未安装，安装 Git for Windows |
| `Permission denied (publickey)` | 配置 GitHub SSH Key |
| `rejected (non-fast-forward)` | 先 `git pull` 解决冲突 |
| `401 Unauthorized` | 使用 Personal Access Token 代替密码 |
| `.gitignore 不生效` | 检查 .gitignore 是否已添加到 git 索引 |

---

## 八、最终检查清单

上传前确认：

- [x] `worknews/` 目录已排除
- [x] `.gitignore` 已创建
- [x] `readme2user.md` 已上传
- [x] 只有必要文件被提交
- [x] 远程分支地址正确

---

