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
#  OpenAlex 抓取（不会被封 IP，GitHub Actions 可直连）
# =============================================================================

import urllib.parse
import urllib.request

OPENALEX_BASE = "https://api.openalex.org"


def setup_proxy():
    """根据 config 设置代理。GitHub Actions 上无需代理。"""
    if not config.USE_PROXY:
        return
    os.environ["HTTP_PROXY"] = config.PROXY_HTTP
    os.environ["HTTPS_PROXY"] = config.PROXY_HTTPS
    print(f"[proxy] 已启用代理: {config.PROXY_HTTP}")


def _oa_get(path: str, params: dict) -> dict:
    """带 mailto 的 OpenAlex GET（进礼貌池速度更快）"""
    if getattr(config, "OPENALEX_EMAIL", ""):
        params = dict(params)
        params["mailto"] = config.OPENALEX_EMAIL
    url = f"{OPENALEX_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ADC-Lab-Publication-Updater (duanjl15@163.com)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_author_id() -> str:
    """解析配置的作者身份，返回 OpenAlex 作者 ID（形如 A5012345678）"""
    # 优先级 1：显式配置的 OpenAlex ID
    oa_id = getattr(config, "OPENALEX_AUTHOR_ID", "").strip()
    if oa_id:
        print(f"[openalex] 使用配置的作者 ID: {oa_id}")
        return oa_id

    # 优先级 2：ORCID → OpenAlex
    orcid = getattr(config, "AUTHOR_ORCID", "").strip()
    if orcid:
        print(f"[openalex] 用 ORCID {orcid} 查作者 ...")
        r = _oa_get(f"/authors/orcid:{orcid}", {})
        aid = r["id"].rsplit("/", 1)[-1]
        print(f"[openalex] 找到 {aid} ({r.get('display_name')})")
        return aid

    # 优先级 3：按名字搜索，挑最高匹配的
    name = getattr(config, "AUTHOR_NAME", "Jingliang Duan")
    print(f"[openalex] 按名字搜索作者: {name}")
    r = _oa_get("/authors", {"search": name, "per_page": 10})
    results = r.get("results", [])
    if not results:
        raise RuntimeError(f"OpenAlex 找不到名字为 '{name}' 的作者")

    # 用机构关键词辅助挑选正确的 Dr. Duan（北京科技大学 / 清华 / Tsinghua / USTB）
    hints = [s.lower() for s in getattr(
        config, "AUTHOR_INSTITUTION_HINTS",
        ["University of Science and Technology Beijing", "USTB", "Tsinghua"],
    )]

    def score(a):
        s = 0
        affs = a.get("last_known_institutions") or []
        for inst in affs:
            nm = (inst.get("display_name") or "").lower()
            for h in hints:
                if h in nm:
                    s += 100
        s += min(a.get("works_count", 0), 50)  # 作品多的加分，但封顶
        return s

    results.sort(key=score, reverse=True)
    best = results[0]
    aid = best["id"].rsplit("/", 1)[-1]
    affs = best.get("last_known_institutions") or []
    aff_name = affs[0].get("display_name") if affs else "(无机构)"
    print(f"[openalex] 挑选: {aid} - {best.get('display_name')} @ {aff_name}")
    print(f"[openalex]   works_count={best.get('works_count')}, 备选 {len(results)-1} 个已跳过")
    return aid


def _format_authors(authorships: list) -> str:
    """把 OpenAlex 的 authorships 数组格式化成 'J Duan, Y Ren, ...' 形式"""
    names = []
    for a in authorships:
        author = a.get("author") or {}
        name = author.get("display_name", "").strip()
        if not name:
            continue
        # 转成 "J Duan" 式缩写（除了我们关心的加粗名字）
        parts = name.split()
        if len(parts) >= 2:
            initials = " ".join(p[0] + "." for p in parts[:-1] if p)
            short = f"{initials} {parts[-1]}"
        else:
            short = name
        names.append(short)
    return ", ".join(names)


def _extract_venue(work: dict) -> str:
    """从 OpenAlex work 对象提取 venue 字段"""
    # arXiv 和 preprint 特殊处理
    loc = work.get("primary_location") or {}
    src = loc.get("source") or {}
    src_type = (src.get("type") or "").lower()
    src_name = (src.get("display_name") or "").strip()

    if work.get("type") == "preprint" or "arxiv" in src_name.lower():
        arxiv_id = ""
        for lid in (work.get("ids") or {}).values():
            if isinstance(lid, str) and "arxiv" in lid.lower():
                arxiv_id = lid.rsplit("/", 1)[-1]
                break
        if arxiv_id:
            return f"arXiv preprint arXiv:{arxiv_id}"
        return "arXiv preprint"

    return src_name


def _best_url(work: dict) -> tuple[str, Optional[str]]:
    """返回 (主链接, 下载链接)"""
    # DOI 优先作为主链接
    doi = work.get("doi")
    primary = doi or work.get("id", "")

    # 找 open access PDF 作为下载链接
    oa = work.get("open_access") or {}
    pdf = oa.get("oa_url")
    if not pdf:
        # 备选：任一 location 的 pdf
        for loc in work.get("locations") or []:
            if loc.get("pdf_url"):
                pdf = loc["pdf_url"]
                break

    return primary, pdf


def fetch_from_scholar(max_results: int) -> list[Pub]:
    """从 OpenAlex 抓取作者全部论文。
    函数名保留 fetch_from_scholar 以避免影响其他模块。
    """
    author_id = _resolve_author_id()

    print(f"[openalex] 正在抓取 {author_id} 的作品列表 ...")
    all_works = []
    page = 1
    per_page = 200  # OpenAlex 上限
    while len(all_works) < max_results:
        r = _oa_get("/works", {
            "filter": f"author.id:{author_id}",
            "per_page": per_page,
            "page": page,
            "sort": "publication_year:desc",
        })
        batch = r.get("results", [])
        if not batch:
            break
        all_works.extend(batch)
        total = r.get("meta", {}).get("count", 0)
        print(f"[openalex]   已拉取 {len(all_works)}/{total}")
        if len(batch) < per_page:
            break
        page += 1

    all_works = all_works[:max_results]
    print(f"[openalex] 共 {len(all_works)} 篇论文，开始格式化 ...")

    pubs: list[Pub] = []
    for i, w in enumerate(all_works):
        try:
            title = (w.get("title") or "").strip()
            if not title:
                continue

            year = w.get("publication_year")
            authorships = w.get("authorships") or []
            authors_str = _format_authors(authorships)
            venue = _extract_venue(w)
            primary_url, download_url = _best_url(w)
            oa_id = w["id"].rsplit("/", 1)[-1]

            pub = Pub(
                title=title,
                authors=authors_str,
                venue=venue,
                year=year,
                url=primary_url,
                pub_url=download_url,
                scholar_id=oa_id,  # 复用这个字段保存 OpenAlex ID
            )
            pubs.append(pub)
            if i < 5 or i % 20 == 0:
                print(f"  [{i+1}/{len(all_works)}] {year or '????'}: {title[:70]}")
        except Exception as e:
            print(f"  [{i+1}] 处理失败: {e}")
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
    """找到指定 h2 下方的 <ol> 元素。
    如果只有 <ul> 没有嵌套 <ol>（如 ArXiv Papers 区块），就在 <ul> 里自动建一个空 <ol>。
    """
    for header in soup.find_all("header"):
        h2 = header.find("h2")
        if h2 and h2.get_text(strip=True) == section_name:
            # 往下找第一个 <ul> 或 <ol>
            node = header
            for _ in range(10):
                node = node.find_next_sibling()
                if node is None:
                    break
                if not hasattr(node, "find"):
                    continue
                # 优先找直接的 <ol>
                ol = node.find("ol") if node.name != "ol" else node
                if ol:
                    return ol
                # 找到了 <ul> 但里面没 <ol>：就地建一个
                if node.name == "ul":
                    new_ol = soup.new_tag("ol")
                    node.append(new_ol)
                    return new_ol
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
