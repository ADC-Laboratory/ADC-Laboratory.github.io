# 修复：从 Google Scholar 切到 OpenAlex

## 为什么要切？

之前跑 GitHub Actions 失败，日志显示：

```
scholarly._proxy_generator.MaxTriesExceededException: Cannot Fetch from Google Scholar.
```

这是 Google Scholar **主动封了 GitHub Actions 的数据中心 IP**。这是一个已知且无法绕过的问题——scholarly 官方文档也承认需要买付费代理服务才能稳定工作。

**OpenAlex** 是学术界的开放替代品：
- 免费、稳定、不封 IP
- 覆盖 2.86 亿篇学术作品
- GitHub Actions 可以直连

## 要替换的文件

把这 4 个文件覆盖到你仓库的对应位置，然后提交：

1. `tool/fetch_scholar.py` —— 抓取模块改成 OpenAlex
2. `tool/config.py` —— 配置支持 OpenAlex
3. `tool/requirements.txt` —— 去掉了 scholarly 依赖
4. `.github/workflows/update_publications.yml` —— 轻微更新

其他文件（`test_offline.py`, `README.md` 等）都是可选更新。

## 提交步骤

```bash
# 复制文件后
git add tool/ .github/
git commit -m "fix: switch from Google Scholar to OpenAlex (no more IP blocking)"
git push
```

## 重新运行 Action

GitHub 仓库 → **Actions** → **Update Publications from OpenAlex** → **Run workflow**

这次应该几分钟就能跑完（OpenAlex 响应很快）。

## 首次跑成功后的优化

第一次跑完，**查看日志**，会看到类似：

```
[openalex] 挑选: A5012345678 - Jingliang Duan @ University of Science and Technology Beijing
```

把那个 `A5012345678` 填回 `tool/config.py` 的 `OPENALEX_AUTHOR_ID`，commit 推上去。

这样以后就不会再每次搜一遍，而是直接用固定的 ID，100% 不会挑错人。
