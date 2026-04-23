# Publication Updater Tool

自动从 Google Scholar 抓取 Dr. Jingliang Duan 的最新出版物，并更新 `publications.html`。

---

## 📁 文件结构

```
tool/
├── fetch_scholar.py    # 主脚本
├── config.py           # 配置文件（修改这里）
├── requirements.txt    # Python 依赖
├── README.md           # 本文档
├── cache/              # 缓存目录（自动创建）
│   └── publications.json
└── backups/            # 备份目录（自动创建，只保留最近 10 份）
    └── publications.YYYYMMDD_HHMMSS.html

.github/workflows/
└── update_publications.yml   # GitHub Actions 自动定时运行
```

---

## 🚀 推荐方案：GitHub Actions 自动运行（不用管大陆网络）

### 为什么推荐

你在国内，Google Scholar 直连不稳。但 **GitHub Actions 的 runner 在海外**，直接能访问 Scholar，这是最省心的方案：

- ✅ 免费
- ✅ 不用买代理
- ✅ 每周自动跑一次（北京时间周一 10:00）
- ✅ 跑完自动 commit 到仓库，网站自动更新
- ✅ 也可以手动点按钮立即执行

### 设置步骤（一次性）

1. **把这个仓库推到 GitHub**（如果还没推）：`ADC-Laboratory.github.io`
2. 确认 `.github/workflows/update_publications.yml` 已经在仓库里
3. 打开 GitHub 仓库 → **Settings** → **Actions** → **General**
4. 在 **Workflow permissions** 区域勾选：
   - ☑ **Read and write permissions**
   - ☑ **Allow GitHub Actions to create and approve pull requests**
5. 保存

### 手动触发一次测试

GitHub 仓库页面 → **Actions** 标签 → 左边选 `Update Publications from Google Scholar` → 点右边 **Run workflow** 按钮。

几分钟后如果成功，会看到一个新的 commit：`chore: auto-update publications from Google Scholar`。

### 调整运行频率

打开 `.github/workflows/update_publications.yml`，改 `cron` 表达式：

```yaml
- cron: "0 2 * * 1"     # 默认：每周一 UTC 02:00
- cron: "0 2 * * *"     # 改成：每天 UTC 02:00
- cron: "0 2 1 * *"     # 改成：每月 1 号 UTC 02:00
```

> 注意：Google Scholar 会对高频请求封 IP，不要设置得太频繁。**一周一次足够了**。

---

## 💻 备选方案：本地手动运行（需要代理）

如果你想在本地电脑上跑，大陆环境需要代理。

### 准备

1. **先开好代理软件**（Clash / V2Ray / 其他），确认能访问 `https://scholar.google.com`
2. 记下代理端口，比如 Clash 默认是 `7890`

### 配置

打开 `tool/config.py`，找到底部的代理设置：

```python
USE_PROXY = True                            # 改成 True
PROXY_HTTP = "http://127.0.0.1:7890"        # 改成你的代理端口
PROXY_HTTPS = "http://127.0.0.1:7890"
```

### 安装 + 运行

```bash
cd tool
pip install -r requirements.txt
cd ..
python tool/fetch_scholar.py
```

首次运行会抓取所有论文，耗时 5-15 分钟（Scholar 限流）。之后会用缓存，增量更新。

### 常用命令

```bash
python tool/fetch_scholar.py              # 正常更新（推荐）
python tool/fetch_scholar.py --dry-run    # 只抓取预览，不修改 HTML
python tool/fetch_scholar.py --force      # 忽略缓存，强制全量重抓
```

### Windows 设置定时任务

想让本地定时跑，用 **任务计划程序**：

1. Win + R → `taskschd.msc`
2. 创建基本任务 → 名字：`Update ADC Publications`
3. 触发器：每周一次，选一个时间
4. 操作：启动程序
   - 程序：`python`
   - 参数：`C:\Users\Administrator\Desktop\ADC-Laboratory.github.io\tool\fetch_scholar.py`
   - 起始于：`C:\Users\Administrator\Desktop\ADC-Laboratory.github.io`
5. 勾选"最高权限运行"

> ⚠️ 本地定时有个前提：**运行那一刻代理必须是开着的**。GitHub Actions 方案没这个问题。

---

## 🔧 配置说明（`tool/config.py`）

| 项 | 说明 |
|---|---|
| `SCHOLAR_USER_ID` | Dr. Duan 的 Scholar ID，URL 里的 `user=xxx` 部分 |
| `MAX_PUBLICATIONS` | 抓取上限，默认 200 |
| `BOLD_AUTHORS` | 哪些名字在作者列表中要加粗，**按需增删实验室成员** |
| `CATEGORY_RULES` | 论文分类关键词，自动把 paper 归到 Journal/Conference/arXiv/Book Chapter |
| `REQUEST_DELAY` | 请求间隔（秒），调低可能被封，默认 2s |

---

## 🛡️ 安全机制

### 1. 只覆盖"自动区"，不碰手写条目

脚本只会修改 `publications.html` 里用注释标记的自动区域：

```html
<ol>
  <!-- 你手写的条目放这里，永远不会被脚本动 -->
  <li>...手写条目...</li>

  <!-- AUTO-SCHOLAR-BEGIN -->
  <li>...脚本自动添加的条目...</li>
  <!-- AUTO-SCHOLAR-END -->
</ol>
```

第一次运行时，脚本会自动在每个 `<ol>` 末尾插入这对标记。你原有的所有条目都会保留在标记**外面**，不会被碰。

### 2. 去重

脚本会读取现有 HTML 里的论文标题，如果发现 Scholar 返回的论文标题已经在页面里（不管在手写区还是自动区），就**不会重复添加**。

### 3. 每次运行自动备份

每次修改前，原文件会备份到 `tool/backups/publications.YYYYMMDD_HHMMSS.html`，只保留最近 10 份。

如果更新出了问题：

```bash
cp tool/backups/publications.20260423_020000.html publications.html
```

---

## ❓ 常见问题

**Q: GitHub Actions 跑失败，提示 Scholar 返回 403 / CAPTCHA？**
A: 很罕见，但如果碰到就等几天再手动重试，或者降低抓取频率。Google 对 GitHub runner IP 段一般很宽松。

**Q: 论文分类不对怎么办？**
A: 改 `tool/config.py` 里的 `CATEGORY_RULES`，加上你需要的关键词。比如某个会议没被识别成 conference，就把会议名加到 conference 那组里。

**Q: 作者名字没被正确加粗？**
A: 改 `BOLD_AUTHORS`。Scholar 返回的作者串有两种常见格式：`J Duan` 和 `J. Duan`，都加进去。中文名（如 `段京良`）也支持。

**Q: 我想回退某次自动更新？**
A: 用 git：`git revert <commit-hash>`；或从 `tool/backups/` 手动恢复。

**Q: 为什么不用官方 Scholar API？**
A: Google Scholar 没有官方 API。`scholarly` 是目前最成熟的非官方爬虫，但有速率限制。
