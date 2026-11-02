# 注意推送流程：
git clone <仓库地址>

切换到开发分支：git checkout develop

严禁直接向 main 或 develop push 代码！

每次开发前先切出你的专属分支：git checkout -b feature/你的名字_功能名

开发完 push 你的分支，然后在网页上发 Pull Request 让我审核合并。”

这份原始文档已经写得非常专业且切中要害了，包含了软件工程里最标准的 `Git Flow` 分支模型和 `Conventional Commits` 提交规范。

为了让这份文档更具**极客范儿**、**排版更清晰**，并补充一些**嵌入式开发的专属避坑点**（比如二进制文件处理），我为你做了全面优化。你可以直接复制以下 Markdown 内容替换原文件。

---

# 📖 Study2everyday 团队 Git 协作规范指南

欢迎加入！为了保证大家在一起写代码、记笔记时高效且不出乱子，请所有成员**严格遵守**以下 Git 协作流程。

> 💡 **核心原则**：永远不要把代码直接推送到 `main` 或 `develop`，这两个分支是团队的“生命线”。

---

## 🌳 一、核心分支模型

我们采用业界标准的 Git Flow 变种，以下为分支职责说明：

*   🔒 `main`：**稳定发布分支**。只存放经过测试的稳定版本，每次合入必须打 Tag（如 `v1.0.0`）。
*   🔒 `develop`：**日常开发主干**。所有人写完的功能都会合并到这里，保持最新。
*   🌿 `feature/*`：**功能/笔记分支**。你平时干活的地方（如 `feature/zhangsan_can_driver`）。
*   🚑 `hotfix/*`：**紧急修复分支**。线上出 Bug 时从 `main` 拉出，修完需同时合入 `main` 和 `develop`。

---

## 🚀 二、日常开发标准流水线（必看）

### Step 1：同步最新代码
每次开始写代码前，必须确保你在最新的 `develop` 分支上。
```bash
git checkout develop
git pull origin develop
```

### Step 2：切出你的专属分支
**千万不要直接改 `develop`**。根据你的任务建一个分支：
```bash
# 命名规范：feature/你的名字_任务名
git checkout -b feature/zhangsan_add_uart_note
```

### Step 3：干活 & 提交
写代码或写笔记，然后提交到本地。
```bash
git status                  # 养成好习惯，看看改了啥，别把编译垃圾加进去
git add <你的文件>           # 不要随便用 git add . 
git commit -m "feat: xxx"   # 必须遵循下方 Commit 规范
```

### Step 4：推送到远程
```bash
# 第一次推这个新分支加 -u，以后就不用加了
git push -u origin feature/zhangsan_add_uart_note
```

### Step 5：发起 PR (Pull Request)
1. 登录 GitHub，找到刚推上去的分支，点击 `Compare & pull request`。
2. **确认方向**：`base: develop` ⬅️ `compare: 你的分支`（千万别合进 main！）。
3. 填写清晰的标题和描述。
4. 点击 `Create pull request`。

### Step 6：合并与清理（极其重要！）
1. 等待他人（或自己）点击 `Merge pull request` -> `Confirm merge`。
2. 在网页上顺手点击 **`Delete branch`** 删除远程草稿分支。
3. **切回本地终端同步并删除本地草稿**：
```bash
git checkout develop
git pull origin develop
git branch -d feature/zhangsan_add_uart_note
```

---

## 📝 三、Commit Message 规范

禁止使用 `update`、`add`、`111` 这种无意义的提交信息。统一使用 `Conventional Commits` 格式：
`<type>(<scope>): <subject>`

*   `feat`：新功能（如 `feat(can): add filter config`）
*   `fix`：修复 Bug（如 `fix(adc): correct channel order`）
*   `docs`：仅修改文档/笔记（如 `docs: add daily note 1102`）
*   `chore`：构建工具、依赖库变动（如 `chore: update gitignore`）
*   `refactor`：重构（既不新增功能也不修 Bug 的代码变动）
*   `test`：增加缺失的测试或者修正已存在的测试

---

## 🛡️ 四、协作铁律与避坑指南（嵌入式专属）

1. **文件隔离（防冲突）**：
   *   在 `notes/daily/` 写笔记时，**必须按自己的名字建文件**（如 `zhangsan_1102.md`）。绝对不要两个人在同一天改同一个 `.md` 文件。
   *   在 `project/` 写代码时，分工明确，不要同时修改同一个 `.c` 文件。

2. **严禁上传编译垃圾**：
   *   仓库已配置 `.gitignore`。严禁提交 `.o`、`.axf`、`.hex`、`.bin`、`Debug/` 等编译产物。
   *   **⚠️ 特殊警告**：LVGL 的字体文件（`.bin`）、大体积图片，尽量转为外置 Flash 烧录，**千万不要直接提交到 Git 仓库**，否则仓库体积会瞬间爆炸。

3. **硬件版本对齐**：
   *   如果涉及原理图版本的固件适配，请从 `develop` 拉取 `board/xxx` 分支（如 `board/stm32_v1.1`）。硬件的引脚宏定义分离，不要污染主干代码。

4. **遇到冲突怎么办？**
   *   如果发 PR 时提示冲突，在本地执行：
   ```bash
   git checkout develop
   git pull origin develop
   git checkout 你的分支
   git merge develop
   # 打开文件，手动解决 <<<<<<< 标记的冲突内容
   git add .
   git commit
   git push
   ```

---

## 💡 五、进阶提示：常用急救命令

### 🟢 救命神技
*   **想看所有分支（含远程）**：`git branch -a`（红色是远程，绿色带星号是当前）。
*   **文件改乱了想还原（未 add）**：`git restore <文件名>`（注意：会丢弃你未提交的修改）。
*   **代码写一半要切分支**：`git stash` （暂存当前修改） -> 切分支 -> `git stash pop`（恢复修改）。
*   **把文件从暂存区拿出来（add 错了）**：`git restore --staged <文件名>`。

### 🔴 千万不要用的危险命令
*   **`git push -f`**（强推，会把别人代码覆盖）。**替代方案**：如果你非要推，用 `git push --force-with-lease`（如果远端有别人的新提交，会失败并提醒你）。
*   **`git clean -fdx`**（会删掉你所有没追踪的文件，包括没入库的代码和新建的文档）。
*   **`git reset --hard`**（丢弃当前所有未提交的修改，救不回来）。

---
**“代码、文档、记录三位一体。”** 祝大家在 Study2everyday 玩得开心，学得扎实！有问题随时在群里喊！