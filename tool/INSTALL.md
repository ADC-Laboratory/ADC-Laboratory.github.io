# Google Scholar 自动更新 - 安装指南

这组文件为 ADC Lab 网站添加了 **自动从 Google Scholar 更新出版物** 的能力。

## 📦 文件清单

需要把这些文件放到你仓库的对应位置：

```
ADC-Laboratory.github.io/
├── tool/
│   ├── fetch_scholar.py       ← 主脚本
│   ├── config.py              ← 配置
│   ├── requirements.txt       ← Python 依赖
│   └── README.md              ← 详细说明
└── .github/
    └── workflows/
        └── update_publications.yml   ← GitHub Actions 自动化
```

## 🎯 快速上手（3 步）

### 1️⃣ 复制文件到仓库

把上面清单里的文件放到对应位置，commit & push 到 GitHub。

### 2️⃣ 打开 GitHub Actions 写权限

仓库页面 → **Settings** → **Actions** → **General** → **Workflow permissions** → 选 **Read and write permissions** → Save。

### 3️⃣ 手动触发一次测试

仓库页面 → **Actions** → 左边 `Update Publications from Google Scholar` → **Run workflow**。

等几分钟，如果成功，仓库里会出现一个新 commit，`publications.html` 已经被更新。

之后每周一 UTC 02:00（北京时间周一 10:00）自动运行。

---

## 💡 为什么这个方案特别适合你

你在大陆，访问 Google Scholar 有限制。**GitHub Actions 的 runner 跑在海外服务器上**，直接就能访问，完全绕开了你本地的网络问题。脚本跑完，还会自动把更新后的 `publications.html` commit 回仓库，**你的网站等于自动更新了**——什么都不用管。

更详细的文档、本地运行方式、配置选项都在 `tool/README.md` 里。
