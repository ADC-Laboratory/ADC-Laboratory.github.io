"""
ADC Lab Publication Updater
===========================

从 Google Scholar 抓取 Dr. Jingliang Duan 的最新出版物，并更新 publications.html。

用法:
    python fetch_scholar.py           # 正常更新
    python fetch_scholar.py --dry-run # 只抓取不写文件，看看效果
    python fetch_scholar.py --force   # 忽略缓存强制重抓全部

依赖 (见 requirements.txt):
    pip install scholarly beautifulsoup4 lxml requests[socks]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString

# 让脚本无论从哪里执行都能找到 config
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import config  # noqa: E402


# =============================================================================
#  数据结构
# =============================================================================

@dataclass
class Pub:
    """一篇论文的结构化表示"""
    title: str
    authors: str          # "J Duan, Y Ren, ..." —— Scholar 返回的原始串
    venue: str            # 发表场所（期刊名/会议名/arxiv）
    year: Optional[int]
    url: str              # scholar 指向的原始论文链接
    pub_url: Optional[str] = None  # 出版商页面/arXiv 页面
    category: str = ""    # journal / conference / arxiv / book_chapter
    scholar_id: str = ""  # scholar 内部 id（用作去重 key）

    def key(self) -> str:
        """用于去重和识别"""
        if self.scholar_id:
            return f"sid:{self.scholar_id}"
        # 标题规范化后做 fallback key
        t = re.sub(r"\W+", "", self.title.lower())
        return f"title:{t}"


# =============================================================================
#  Scholar 抓取
# =============================================================================

def setup_proxy():
    """根据 config 设置代理。GitHub Actions 上无需代理。"""
    if not config.USE_PROXY:
        return
    os.environ["HTTP_PROXY"] = config.PROXY_HTTP
    os.environ["HTTPS_PROXY"] = config.PROXY_HTTPS
    print(f"[proxy] 已启用代理: {config.PROXY_HTTP}")


def fetch_from_scholar(max_results: int) -> list[Pub]:
    """用 scholarly 库抓取作者的所有论文"""
    from scholarly import scholarly, ProxyGenerator

    # 如果用了代理，也告诉 scholarly 使用
    if config.USE_PROXY:
        pg = ProxyGenerator()
        pg.SingleProxy(http=config.PROXY_HTTP, https=config.PROXY_HTTPS)
        scholarly.use_proxy(pg)

    print(f"[scholar] 正在查找作者 {config.SCHOLAR_USER_ID} ...")
    author = scholarly.search_author_id(config.SCHOLAR_USER_ID)
    author = scholarly.fill(author, sections=["publications"])

    pubs_raw = author.get("publications", [])
    print(f"[scholar] 作者共有 {len(pubs_raw)} 篇论文，将抓取前 {min(max_results, len(pubs_raw))} 篇详情")

    pubs: list[Pub] = []
    for i, p in enumerate(pubs_raw[:max_results]):
        try:
            # 填充详细信息（需要额外请求，会有速率限制）
            filled = scholarly.fill(p)
            bib = filled.get("bib", {})

            # 解析年份
            year = None
            raw_year = bib.get("pub_year") or bib.get("year")
            if raw_year:
                try:
                    year = int(str(raw_year)[:4])
                except ValueError:
                    pass

            pub = Pub(
                title=bib.get("title", "").strip(),
                authors=bib.get("author", "").strip(),
                venue=(bib.get("journal") or bib.get("venue")
                       or bib.get("conference") or bib.get("booktitle") or "").strip(),
                year=year,
                url=filled.get("pub_url", "") or filled.get("eprint_url", ""),
                pub_url=filled.get("pub_url") or filled.get("eprint_url"),
                scholar_id=filled.get("author_pub_id", ""),
            )
            pubs.append(pub)
            print(f"  [{i+1}/{max_results}] {pub.year or '????'}: {pub.title[:70]}")
            time.sleep(config.REQUEST_DELAY)
        except Exception as e:
            print(f"  [{i+1}] 抓取失败: {e}")
            continue

    return pubs


# =============================================================================
#  分类 + 作者加粗
# =============================================================================

def categorize(pub: Pub) -> str:
    """根据 venue 关键词给论文分类"""
    v = (pub.venue or "").lower()
    for cat, keywords in config.CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in v:
                return cat
    return config.DEFAULT_CATEGORY


def bold_authors(authors_str: str) -> str:
    """在作者串中把本组成员用 <b>...</b> 包裹"""
    # 按长度降序排序，先匹配长名字，避免 "J Duan" 吃掉 "Jingliang Duan"
    names = sorted(set(config.BOLD_AUTHORS), key=len, reverse=True)
    result = authors_str
    for name in names:
        # 用正则，大小写不敏感，边界用非字母数字
        pattern = re.compile(
            r"(?<![\w\u4e00-\u9fff])" + re.escape(name) + r"(?![\w\u4e00-\u9fff])",
            re.IGNORECASE,
        )
        # 避免重复加粗
        result = pattern.sub(lambda m: f"<BOLD>{m.group(0)}</BOLD>", result)
    # 统一转成 <b>（先用占位符避免嵌套）
    result = result.replace("<BOLD>", "<b>").replace("</BOLD>", "</b>")
    return result


# =============================================================================
#  HTML 片段生成
# =============================================================================

def render_li(pub: Pub) -> str:
    """把一篇论文渲染成 <li>…</li> 片段"""
    authors_html = bold_authors(pub.authors)

    # 标题部分：有链接就加链接，没链接就纯文本
    if pub.url:
        title_html = f'<a href="{pub.url}">"{pub.title},"</a>'
    else:
        title_html = f'"{pub.title},"'

    # venue + year
    venue_bits = []
    if pub.venue:
        venue_bits.append(pub.venue)
    if pub.year:
        venue_bits.append(str(pub.year))
    venue_html = ", ".join(venue_bits) + "." if venue_bits else ""

    # Download 链接（如果有 pub_url）
    download_html = ""
    if pub.pub_url:
        download_html = f'&nbsp;&nbsp;&nbsp;&nbsp;<a href="{pub.pub_url}">Download</a>'

    return (
        '<li style="text-align: justify;"> '
        f'{authors_html}, {title_html} {venue_html}{download_html}'
        '</li>'
    )


# =============================================================================
#  HTML 更新
# =============================================================================

# 四个区块的 h2 标题 → 内部分类键
SECTION_MAP = {
    "Journal": "journal",
    "Book Chapter": "book_chapter",
    "ArXiv Papers": "arxiv",
    "Conference Papers": "conference",
}

# 脚本管理区块的标记注释。只有在这对注释之间的条目会被脚本覆盖/更新，
# 手动写的条目留在注释外面不会被动。
BEGIN_MARK = "<!-- AUTO-SCHOLAR-BEGIN -->"
END_MARK = "<!-- AUTO-SCHOLAR-END -->"


def extract_existing_keys(soup: BeautifulSoup) -> set[str]:
    """从现有 HTML 里提取所有论文的标题作为去重 key（用于避免自动区重复添加手动条目）"""
    keys = set()
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        # 提取引号里的标题
        m = re.search(r'["\u201c\u201d]([^"\u201c\u201d]{10,})["\u201c\u201d]', text)
        if m:
            t = re.sub(r"\W+", "", m.group(1).lower())
            keys.add(f"title:{t}")
    return keys


def find_section_ol(soup: BeautifulSoup, section_name: str):
    """找到指定 h2 下方的 <ol> 元素"""
    for header in soup.find_all("header"):
        h2 = header.find("h2")
        if h2 and h2.get_text(strip=True) == section_name:
            # 往下找第一个 <ol>
            node = header
            for _ in range(10):
                node = node.find_next_sibling()
                if node is None:
                    break
                ol = node.find("ol") if hasattr(node, "find") else None
                if ol:
                    return ol
    return None


def update_html(pubs: list[Pub], html_path: Path, dry_run: bool = False) -> None:
    """把论文按分类插入到 publications.html 对应区块"""
    print(f"[html] 读取 {html_path}")
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    existing_keys = extract_existing_keys(soup)
    print(f"[html] 现有论文条目 {len(existing_keys)} 条")

    # 按分类分组 + 按年份降序
    by_category: dict[str, list[Pub]] = {}
    for p in pubs:
        p.category = categorize(p)
        by_category.setdefault(p.category, []).append(p)
    for cat in by_category:
        by_category[cat].sort(key=lambda x: (x.year or 0), reverse=True)

    added_count = 0
    for section_title, cat_key in SECTION_MAP.items():
        ol = find_section_ol(soup, section_title)
        if ol is None:
            print(f"[html] 警告：找不到区块 <h2>{section_title}</h2>，跳过")
            continue

        # 找/建自动管理区
        auto_block = _get_or_create_auto_block(ol, soup)

        # 清空自动区
        for child in list(auto_block["content"]):
            child.extract()

        section_pubs = by_category.get(cat_key, [])
        added_here = 0
        for pub in section_pubs:
            if pub.key() in existing_keys:
                continue  # 手动区已有，不重复
            li_html = render_li(pub)
            li_soup = BeautifulSoup(li_html, "lxml")
            # lxml 会包 html/body，取真正的 <li>
            li_tag = li_soup.find("li")
            if li_tag:
                auto_block["end_mark"].insert_before(li_tag)
                auto_block["end_mark"].insert_before("\n\t\t\t\t\t\t\t\t\t\t\t")
                added_here += 1

        print(f"[html] [{section_title}] 自动添加 {added_here} 条")
        added_count += added_here

    print(f"[html] 总共新增/更新 {added_count} 条自动条目")

    if dry_run:
        print("[dry-run] 未写入文件")
        return

    # 备份
    backup_dir = Path(config.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"publications.{stamp}.html"
    shutil.copy2(html_path, backup_path)
    print(f"[backup] 已备份到 {backup_path}")

    # 清理旧备份，只保留最近 10 个
    backups = sorted(backup_dir.glob("publications.*.html"))
    for old in backups[:-10]:
        old.unlink()

    # 写回
    html_path.write_text(str(soup), encoding="utf-8")
    print(f"[html] 已更新 {html_path}")


def _get_or_create_auto_block(ol, soup):
    """在 <ol> 里找到（或创建）自动管理区域标记对
    返回 dict: { 'begin_mark': Comment, 'end_mark': Comment, 'content': [...] }
    """
    from bs4 import Comment

    begin = None
    end = None
    for c in ol.children:
        if isinstance(c, Comment):
            s = c.string.strip() if c.string else ""
            if s == BEGIN_MARK.strip("<!- >"):
                begin = c
            elif s == END_MARK.strip("<!- >"):
                end = c

    if begin is None or end is None:
        # 创建一对标记，插到 ol 末尾
        begin = Comment(" AUTO-SCHOLAR-BEGIN ")
        end = Comment(" AUTO-SCHOLAR-END ")
        ol.append("\n\t\t\t\t\t\t\t\t\t\t")
        ol.append(begin)
        ol.append("\n")
        ol.append(end)
        ol.append("\n\t\t\t\t\t\t\t\t\t")

    # 收集两标记之间的内容
    content = []
    node = begin.next_sibling
    while node is not None and node is not end:
        content.append(node)
        node = node.next_sibling

    return {"begin_mark": begin, "end_mark": end, "content": content}


# =============================================================================
#  缓存
# =============================================================================

def load_cache() -> list[Pub]:
    cache_path = Path(config.CACHE_FILE)
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return [Pub(**item) for item in data]
    except Exception as e:
        print(f"[cache] 读取失败: {e}")
        return []


def save_cache(pubs: list[Pub]) -> None:
    cache_path = Path(config.CACHE_FILE)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps([asdict(p) for p in pubs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[cache] 已保存 {len(pubs)} 条到 {cache_path}")


# =============================================================================
#  主流程
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="只抓取不写文件，看看效果")
    parser.add_argument("--force", action="store_true",
                        help="忽略缓存，强制重抓")
    parser.add_argument("--html", default=None,
                        help="指定 publications.html 路径（默认仓库根目录）")
    args = parser.parse_args()

    setup_proxy()

    # 定位 publications.html
    html_path = Path(args.html) if args.html else (_HERE.parent / config.PUBLICATIONS_HTML)
    if not html_path.exists():
        print(f"错误：找不到 {html_path}")
        sys.exit(1)

    # 抓取
    if args.force:
        pubs = fetch_from_scholar(config.MAX_PUBLICATIONS)
    else:
        cached = load_cache()
        if cached:
            print(f"[cache] 从缓存加载 {len(cached)} 条")
            # 轻量抓取：只查作者首页的最新论文来决定是否需要全量更新
            pubs = fetch_from_scholar(config.MAX_PUBLICATIONS)
        else:
            pubs = fetch_from_scholar(config.MAX_PUBLICATIONS)

    if not pubs:
        print("未抓到任何论文，退出")
        sys.exit(1)

    save_cache(pubs)
    update_html(pubs, html_path, dry_run=args.dry_run)
    print("[done] 完成")


if __name__ == "__main__":
    main()
