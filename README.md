# study2everyday

## 项目简介
这是一个每天学习打卡的记录仓库。
目的是想锻炼 Git 使用以及代码仓库管理。

## 目录规划
- `project/`：存放个人小项目（如 STM32/ESP32 练手项目）
- `notes/`：学习笔记与每日记录

## 目录结构
```text
study2everyday/
├── README.md
├── notes/
│   ├── README.md
│   └── daily/
│       └── README.md
├── project/
│   └── README.md
└── .gitignore   (可按需新增)
```

## 记录方式
### 1）学习笔记
在 `notes/` 下记录每天学习的内容，包括：
- 学习主题
- 重点知识点
- 遇到的问题
- 解决思路
- 今日收获

### 2）项目练习
在 `project/` 下记录每个小项目的目标、实现思路、代码文件和测试结果。

## 分支规范
- `main`：稳定发布分支
- `develop`：日常开发分支
- `feature/*`：功能开发分支

## 发布记录 (Releases)
- `v0.1.0`：初始化仓库与 Git 规范 (待打 Tag)

## 今日建��
- 每天在 `notes/daily/` 中新增一份当日学习记录
- 每个小项目在 `project/` 中建立独立目录
- 先从简单项目入手，逐步建立代码、文档、记录三位一体的学习习惯
