# Publication Updater Tool

自动从 **OpenAlex** 抓取 Dr. Jingliang Duan 的最新出版物，并更新 `publications.html`。

---

## 🔄 为什么从 Google Scholar 切到 OpenAlex？

之前用 `scholarly` 抓 Google Scholar，但 Google Scholar 会封数据中心 IP，
GitHub Actions 跑 10 分钟后稳定报 `MaxTriesExceededException`。

**OpenAlex 是学术界的开放替代品：**
- 免费、无 API key 要求（带 email 进礼貌池响应更快）
- 覆盖 **2.86 亿篇学术作品**，几乎所有有 DOI/arXiv ID 的论文都在
- 没有反爬机制，GitHub Actions 可以稳定直连
- API 干净清晰，几秒钟就能抓完一个作者的全部作品

---

## 📁 文件结构

```
tool/
├── fetch_scholar.py    # 主脚本（名字保留，实际走 OpenAlex）
├── config.py           # 配置文件
├── test_offline.py     # 离线测试脚本
├── requirements.txt    # Python 依赖（只要 beautifulsoup4 + lxml）
├── README.md           # 本文档
├── cache/              # 缓存（自动创建）
└── backups/            # 备份（自动创建，保留最近 10 份）

.github/workflows/
└── update_publications.yml   # GitHub Actions 定时任务
```

---

## 🚀 首次设置（3 步）

### 1. 确认 Actions 写入权限

GitHub 仓库 → **Settings** → **Actions** → **General** → **Workflow permissions**：
- ☑ **Read and write permissions**

### 2.（可选但推荐）固化作者 ID

脚本第一次跑会按名字搜索作者。为了避免万一匹配错人，建议固化 OpenAlex ID：

1. 访问：`https://api.openalex.org/authors?search=Jingliang%20Duan`
2. 找到 Dr. Duan（应该有 "University of Science and Technology Beijing" 或 "Tsinghua" 的 affiliation）
3. 复制 `"id"` 字段的末尾部分，形如 `A5012345678`
4. 填到 `tool/config.py`：
   ```python
   OPENALEX_AUTHOR_ID = "A5012345678"
   ```

不填也可以——脚本会按名字搜 + 机构关键词打分自动挑。但填上更保险。

### 3. 手动触发一次

仓库 **Actions** → **Update Publications from OpenAlex** → **Run workflow**。

成功的话会自动 commit：`chore: auto-update publications from OpenAlex (2026-...)`

之后每周一北京时间 10:00 自动跑。

---

## 💻 本地测试

**不需要代理**——OpenAlex 在国内直连正常。

### 离线测试（只验证 HTML 逻辑，不联网）

```bash
cd tool
pip install -r requirements.txt
python test_offline.py
```

会生成 `tool/test_output/publications.TEST.html`，浏览器打开看效果。

### 真实抓取（联网）

```bash
# 预览模式，不改文件
python tool/fetch_scholar.py --dry-run

# 正式运行
python tool/fetch_scholar.py

# 忽略缓存，强制重抓
python tool/fetch_scholar.py --force
```

---

## 🔧 配置说明（`tool/config.py`）

| 配置项 | 说明 |
|---|---|
| `OPENALEX_AUTHOR_ID` | OpenAlex 作者 ID（推荐填，最精确） |
| `AUTHOR_ORCID` | 如果 Dr. Duan 有 ORCID 也可以填，优先级高于名字搜索 |
| `AUTHOR_NAME` | 姓名备选 |
| `AUTHOR_INSTITUTION_HINTS` | 同名作者里挑人用的机构关键词 |
| `OPENALEX_EMAIL` | 请求 header 里的 email，进礼貌池响应更快 |
| `BOLD_AUTHORS` | 自动加粗的作者名字列表，按需增删实验室成员 |
| `CATEGORY_RULES` | 分类关键词，把论文归到 Journal/Conference/arXiv/Book Chapter |
| `MAX_PUBLICATIONS` | 抓取上限，默认 500 |

---

## 🛡️ 安全机制

### 1. 只覆盖"自动区"

脚本只会修改 `publications.html` 里用注释标记的自动区域：

```html
<ol>
  <li>...你手写的条目...</li>       <!-- 永远不会被脚本动 -->

  <!-- AUTO-SCHOLAR-BEGIN -->
  <li>...脚本自动添加的...</li>
  <!-- AUTO-SCHOLAR-END -->
</ol>
```

首次运行会自动在每个 `<ol>` 末尾插入这对标记。

### 2. 自动去重

如果 OpenAlex 返回的论文标题已经在 HTML 里（不管是手写还是自动区），脚本不会重复添加。

### 3. 每次自动备份

修改前会把原文件存到 `tool/backups/publications.YYYYMMDD_HHMMSS.html`，保留最近 10 份。

回滚：`cp tool/backups/publications.xxx.html publications.html`

---

## ❓ 常见问题

**Q: OpenAlex 会不会少收录论文？**
A: OpenAlex 整合了 Crossref、DOAJ、arXiv、PubMed 等主流索引，覆盖率和 Scholar 非常接近。新论文通常几天到一周内收录。偶尔有个别会议没收录，可以手动加到 `<!-- AUTO-SCHOLAR-BEGIN -->` 标记**外面**的手写区。

**Q: 论文分类不对怎么办？**
A: 改 `tool/config.py` 里的 `CATEGORY_RULES`。

**Q: 某个人没被加粗？**
A: 改 `BOLD_AUTHORS`。OpenAlex 返回的作者名会被脚本自动压缩成 `J. Duan` 格式。

**Q: 想取消定时只保留手动？**
A: 改 `.github/workflows/update_publications.yml`，删掉 `schedule:` 那两行。

**Q: 我怎么回退某次自动更新？**
A: `git revert <commit-hash>` 或者从 `tool/backups/` 恢复。
