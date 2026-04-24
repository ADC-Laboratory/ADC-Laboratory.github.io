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
    authors: str          # "J Duan, Y Ren, ..."
    venue: str
    year: Optional[int]
    url: str              # 主链接（DOI 优先）
    pub_url: Optional[str] = None  # Download 链接
    category: str = ""    # journal / conference / arxiv / book_chapter
    oa_id: str = ""       # OpenAlex work ID
    is_preprint: bool = False
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None  # 如果能找到对应的 arXiv ID
    # 来自 OpenAlex 的结构化类型，用于精确分类
    work_type: str = ""   # journal-article / proceedings-article / book-chapter / book / preprint / ...
    source_type: str = "" # journal / conference / book / book series / ebook platform / repository / ...

    def title_key(self) -> str:
        """规范化标题作为去重 key。
        全 lowercase、去所有非字母数字字符、压缩空格，避免标点/大小写差异导致重复。
        """
        return re.sub(r"\W+", "", self.title.lower())


@dataclass
class ExistingEntry:
    """从现有 HTML 里解析出的一条论文条目"""
    title_key: str
    year: Optional[int]
    raw_html: str         # 完整的 <li>...</li> HTML 原文
    section: str          # "Journal" / "Conference Papers" / ...
    is_auto: bool = False # 是否由脚本生成（下次可被覆盖）


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

    # 用机构关键词辅助挑选正确的 Dr. Duan
    # 段老师工作/访学经历：USTB（现职）、清华（博士）、NUS、UC Berkeley
    hints = [s.lower() for s in getattr(
        config, "AUTHOR_INSTITUTION_HINTS",
        [
            "University of Science and Technology Beijing", "USTB",
            "Tsinghua",
            "National University of Singapore", "NUS",
            "University of California, Berkeley", "UC Berkeley", "Berkeley",
        ],
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


def _best_url(work: dict) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """返回 (主链接, 下载链接, doi, arxiv_id)"""
    doi = work.get("doi")
    primary = doi or work.get("id", "")

    # 找 open access PDF 作为下载链接
    oa = work.get("open_access") or {}
    pdf = oa.get("oa_url")
    if not pdf:
        for loc in work.get("locations") or []:
            if loc.get("pdf_url"):
                pdf = loc["pdf_url"]
                break

    # 找 arXiv ID
    arxiv_id = None
    for loc in (work.get("locations") or []):
        src = loc.get("source") or {}
        src_name = (src.get("display_name") or "").lower()
        if "arxiv" in src_name:
            landing = loc.get("landing_page_url") or ""
            m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", landing)
            if m:
                arxiv_id = m.group(1)
                break

    return primary, pdf, doi, arxiv_id


def _matches_author_institutions(work: dict, author_id: str, hints: list[str]) -> bool:
    """检查 work 里 Dr. Duan 对应的 authorship 是否关联到白名单机构
    
    - 找到 authorships 里 author.id == target author_id 的那一条
    - 查它的 institutions 里有没有任一关键词匹配
    - 如果 authorships 里没有匹配的机构信息（空），默认通过（不误杀）
    """
    target_url_suffix = author_id  # e.g. "A5067909017"
    hints_lower = [h.lower() for h in hints]

    for a in work.get("authorships") or []:
        author = a.get("author") or {}
        aid = (author.get("id") or "").rsplit("/", 1)[-1]
        if aid != target_url_suffix:
            continue
        # 这就是 Dr. Duan 的 authorship
        insts = a.get("institutions") or []
        if not insts:
            # 没有机构信息：给 benefit of doubt（OpenAlex 常常没抓全）
            return True
        for inst in insts:
            name = (inst.get("display_name") or "").lower()
            for h in hints_lower:
                if h in name:
                    return True
        # 有机构但都不匹配：拒绝
        return False
    # 没找到 target authorship（不应该，但保险起见）
    return True


def _should_include(work: dict, author_id: str) -> tuple[bool, str]:
    """判断 work 是否应该被包含。返回 (是否包含, 若不包含的原因)"""
    oa_id = work["id"].rsplit("/", 1)[-1]

    # 规则 3：黑名单
    excludes = getattr(config, "EXCLUDE_OA_IDS", []) or []
    if oa_id in excludes:
        return False, "在 EXCLUDE_OA_IDS 黑名单中"

    # 规则 1：年份
    min_year = getattr(config, "MIN_YEAR", 0) or 0
    year = work.get("publication_year") or 0
    if min_year and year and year < min_year:
        return False, f"年份 {year} < MIN_YEAR {min_year}"

    # 规则 2：机构
    if getattr(config, "REQUIRE_INSTITUTION_MATCH", False):
        hints = getattr(config, "AUTHOR_INSTITUTION_HINTS", []) or []
        if hints and not _matches_author_institutions(work, author_id, hints):
            affs = []
            for a in work.get("authorships") or []:
                author = a.get("author") or {}
                aid = (author.get("id") or "").rsplit("/", 1)[-1]
                if aid == author_id:
                    for inst in a.get("institutions") or []:
                        affs.append(inst.get("display_name", "?"))
                    break
            return False, f"机构不匹配（该论文 Duan 关联机构：{affs or '无'}）"

    return True, ""


def fetch_from_scholar(max_results: int) -> list[Pub]:
    """从 OpenAlex 抓取作者全部论文。"""
    author_id = _resolve_author_id()

    print(f"[openalex] 正在抓取 {author_id} 的作品列表 ...")
    all_works = []
    page = 1
    per_page = 200
    while len(all_works) < max_results * 2:  # 多抓一些因为会被过滤掉一批
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

    print(f"[openalex] 共 {len(all_works)} 篇 raw works，开始过滤 ...")

    # 过滤阶段
    filter_stats = {"year": 0, "institution": 0, "blacklist": 0}
    filtered_works = []
    for w in all_works:
        ok, reason = _should_include(w, author_id)
        if not ok:
            if "MIN_YEAR" in reason:
                filter_stats["year"] += 1
            elif "机构" in reason:
                filter_stats["institution"] += 1
            elif "黑名单" in reason:
                filter_stats["blacklist"] += 1
            title = (w.get("title") or "")[:60]
            print(f"  [跳过] {w.get('publication_year', '?')}: {title} — {reason}")
            continue
        filtered_works.append(w)

    if any(filter_stats.values()):
        print(f"[filter] 过滤统计：年份 {filter_stats['year']} / "
              f"机构 {filter_stats['institution']} / 黑名单 {filter_stats['blacklist']}")

    filtered_works = filtered_works[:max_results]
    print(f"[openalex] 过滤后 {len(filtered_works)} 篇，开始格式化 ...")

    pubs: list[Pub] = []
    for i, w in enumerate(filtered_works):
        try:
            title = (w.get("title") or "").strip()
            if not title:
                continue

            year = w.get("publication_year")
            authorships = w.get("authorships") or []
            authors_str = _format_authors(authorships)
            venue = _extract_venue(w)
            primary_url, download_url, doi, arxiv_id = _best_url(w)
            oa_id = w["id"].rsplit("/", 1)[-1]

            # 判断是不是预印本（同时保存结构化类型用于分类）
            work_type = (w.get("type") or "").lower()
            src = (w.get("primary_location") or {}).get("source") or {}
            src_name = (src.get("display_name") or "").lower()
            src_type = (src.get("type") or "").lower()
            is_preprint = (
                work_type in {"preprint", "posted-content"}
                or "arxiv" in src_name
                or venue.lower().startswith("arxiv")
            )

            pub = Pub(
                title=title,
                authors=authors_str,
                venue=venue,
                year=year,
                url=primary_url,
                pub_url=download_url,
                oa_id=oa_id,
                is_preprint=is_preprint,
                doi=doi,
                arxiv_id=arxiv_id,
                work_type=work_type,
                source_type=src_type,
            )
            pubs.append(pub)
        except Exception as e:
            print(f"  [{i+1}] 处理失败: {e}")
            continue

    print(f"[openalex] 成功解析 {len(pubs)} 篇")

    # 过滤：最小年份 + 黑名单
    pubs = _apply_filters(pubs)

    return pubs


def _apply_filters(pubs: list[Pub]) -> list[Pub]:
    """按 config 里的过滤规则过滤论文。用于剔除 OpenAlex 作者消歧错误归入的论文。"""
    min_year = getattr(config, "MIN_YEAR", 0) or 0
    exclude_ids = set(getattr(config, "EXCLUDE_WORK_IDS", []) or [])
    exclude_keywords = [k.lower() for k in (getattr(config, "EXCLUDE_TITLE_KEYWORDS", []) or [])]

    kept = []
    dropped_by_year = []
    dropped_by_id = []
    dropped_by_kw = []

    for p in pubs:
        # 年份过滤
        if min_year and p.year and p.year < min_year:
            dropped_by_year.append(p)
            continue
        # ID 黑名单
        if p.oa_id in exclude_ids:
            dropped_by_id.append(p)
            continue
        # 标题关键词黑名单
        title_lower = p.title.lower()
        if any(kw in title_lower for kw in exclude_keywords):
            dropped_by_kw.append(p)
            continue
        kept.append(p)

    if dropped_by_year:
        print(f"[filter] 按最小年份 ({min_year}) 过滤掉 {len(dropped_by_year)} 篇：")
        for p in dropped_by_year:
            print(f"    - [{p.year}] {p.oa_id}: {p.title[:80]}")
        print(f"  提示：如果有误过滤，调低 config.MIN_YEAR；")
        print(f"       如果确认是同名作者误归，可放心过滤。")
    if dropped_by_id:
        print(f"[filter] 按 ID 黑名单过滤掉 {len(dropped_by_id)} 篇")
    if dropped_by_kw:
        print(f"[filter] 按标题关键词过滤掉 {len(dropped_by_kw)} 篇")

    # 额外的可疑提示：即使通过过滤，也标注一些可能误归的论文
    _suggest_suspicious(kept)

    print(f"[filter] 过滤后剩余 {len(kept)} 篇")
    return kept


def _suggest_suspicious(pubs: list[Pub]) -> None:
    """检查剩余论文，提示可能误归的（基于：作者列表里没有已知的实验室成员/合作者）"""
    # 已知的 Dr. Duan 合作者关键词（姓即可）
    known_collaborators = [
        "duan", "li", "guan", "ren", "sun", "cheng", "ma", "chen", "zou",
        "yin", "wang", "zhang", "zheng", "zhou", "yu", "gu", "xu", "peng",
        "lin", "hou", "jiang", "xiao", "yan", "jiao", "kong", "ji", "wei",
        "yang", "song", "zhao", "cao", "liu", "mu", "dai", "ge",
    ]

    suspicious = []
    for p in pubs:
        # 把作者列表小写化
        authors_lower = p.authors.lower()
        # 如果作者列表里一个已知合作者都没匹配到，就可疑
        if not any(c in authors_lower for c in known_collaborators):
            suspicious.append(p)

    if suspicious:
        print(f"[filter] 以下 {len(suspicious)} 篇的作者列表看起来不像 Dr. Duan 圈子，")
        print("         如果是误归，可以加到 config.EXCLUDE_WORK_IDS：")
        for p in suspicious[:10]:
            print(f"    ? [{p.year}] {p.oa_id}: {p.title[:80]}")
            print(f"      作者: {p.authors[:120]}")


# =============================================================================
#  分类 + 作者加粗
# =============================================================================

def _category_from_doi(doi: str) -> Optional[str]:
    """从 DOI/URL pattern 推断论文类型。
    
    策略：各大出版商的 DOI 有固定 pattern，用正则识别。
    返回 "conference"/"journal"/None（无法判断时）。
    """
    if not doi:
        return None
    d = doi.lower()

    # ---- IEEE Xplore (10.1109) ----
    # 会议: 10.1109/{abbr}{conf_num}.{year}...   e.g. 10.1109/cdc57313.2025.xxx
    # 期刊: 10.1109/{abbr}.{year}...             e.g. 10.1109/tnnls.2024.xxx
    m = re.search(r"10\.1109/([a-z]+)(\d*)\.", d)
    if m:
        return "conference" if m.group(2) else "journal"

    # ---- ACM (10.1145) ----
    # ACM 会议论文集的 DOI 通常是 10.1145/{7-digit-conf-id}.{paper-id}
    # 期刊的 DOI 通常包含期刊短名，如 10.1145/3528223 (TOG)，结构单调
    # 最可靠信号：ACM 会议 DOI 后接 doi.org 的论文常来自 dl.acm.org/doi/{doi}
    # 这里简单用：DOI 路径段数量 ≥ 2 且第一段是纯数字的 → 会议
    m = re.search(r"10\.1145/(\d+)\.(\d+)", d)
    if m:
        return "conference"

    # ---- AAAI (10.1609/aaai) ----
    # AAAI 的 DOI 形如 10.1609/aaai.v37i5.25865 或 10.1609/aimag.v44i3.xxxx
    # aaai.* → 会议；aimag.* → 期刊 (AI Magazine)
    if re.search(r"10\.1609/aaai\.", d):
        return "conference"
    if re.search(r"10\.1609/aimag\.", d):
        return "journal"

    # ---- JMLR / PMLR 系列（ICML、AISTATS、CoLT、CoRL 等走 PMLR）----
    # PMLR 没有 DOI，用 URL 判断
    # proceedings.mlr.press / openreview.net → 基本都是会议
    if "proceedings.mlr.press" in d or "openreview.net" in d:
        return "conference"

    # ---- OpenReview (ICLR / NeurIPS / 部分 workshop) ----
    # openreview.net/forum?id=xxx → 通常会议（NeurIPS、ICLR 的正式渠道）
    # 上面的 "openreview.net" 规则已覆盖

    # ---- Springer LNCS 会议集 (10.1007/978-...) ----
    # 注意：这也可能是 book chapter，不能强行归类
    # 让它回落到 work_type / venue 判断

    # ---- Elsevier journals (10.1016/j.xxx) ----
    # j.xxx 基本都是期刊；j.ifacol.xxx 是 IFAC 会议(IFAC-PapersOnLine 算 proceedings)
    m = re.search(r"10\.1016/j\.([a-z]+)", d)
    if m:
        short = m.group(1)
        if short in {"ifacol"}:  # IFAC-PapersOnLine (会议)
            return "conference"
        return "journal"  # 其他 Elsevier 期刊

    # ---- Wiley journals (10.1002 / 10.1049) ----
    # 多为期刊，没有明显会议 pattern；不强行判断让回落

    return None


def categorize(pub: Pub) -> str:
    """给论文分类。优先用 OpenAlex 返回的结构化类型（work_type / source_type），
    然后用 DOI 启发式，最后用 venue 文本关键词。
    """
    # 1. Preprint 永远归 arxiv
    if pub.is_preprint:
        return "arxiv"

    # 2. OpenAlex 的 work type（最权威）
    wt = (pub.work_type or "").lower()
    if wt in ("book-chapter", "book", "reference-entry", "monograph"):
        return "book_chapter"
    if wt == "proceedings-article":
        return "conference"
    if wt == "journal-article":
        return "journal"

    # 3. source type 辅助判断
    st = (pub.source_type or "").lower()
    if st in ("book", "book series", "ebook platform"):
        return "book_chapter"
    if st == "conference":
        return "conference"
    if st == "journal":
        return "journal"
    if st == "repository":
        return "arxiv"

    # 4. DOI / URL 启发式（针对 OpenAlex 没标 type 的论文特别有效）
    for candidate in [pub.doi or "", pub.url or "", pub.pub_url or ""]:
        doi_cat = _category_from_doi(candidate)
        if doi_cat:
            return doi_cat

    # 5. 回落到 venue 关键词匹配
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
#  渲染：Pub 对象 → <li> HTML
# =============================================================================

def render_li(pub: Pub) -> str:
    """把一篇论文渲染成 <li>…</li> 片段。
    加 data-src 属性标记为脚本生成，下次运行时可被覆盖更新。
    """
    authors_html = bold_authors(pub.authors)

    # 标题部分
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

    # 如果是正式发表版本但也有 arXiv 版，附加 arXiv 链接
    extras = ""
    if not pub.is_preprint and pub.arxiv_id:
        extras += f' (arXiv: <a href="https://arxiv.org/abs/{pub.arxiv_id}">{pub.arxiv_id}</a>)'

    # Download 链接
    download_html = ""
    if pub.pub_url:
        download_html = f'&nbsp;&nbsp;&nbsp;&nbsp;<a href="{pub.pub_url}">Download</a>'

    return (
        f'<li style="text-align: justify;" data-src="openalex:{pub.oa_id}" data-year="{pub.year or ""}"> '
        f'{authors_html}, {title_html} {venue_html}{extras}{download_html}'
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
# 反向映射
CATEGORY_TO_SECTION = {v: k for k, v in SECTION_MAP.items()}


def _normalize_title(text: str) -> str:
    """从任意字符串提取规范化标题 key"""
    return re.sub(r"\W+", "", text.lower())


def _extract_title_from_li(li) -> Optional[str]:
    """从 <li> 里提取引号包围的论文标题"""
    text = li.get_text(" ", strip=True)
    # 匹配 "..."  或 "..." (英文卷曲引号)
    m = re.search(r'["\u201c]([^"\u201c\u201d]{10,})["\u201d"]', text)
    if m:
        return m.group(1).strip().rstrip(",").strip()
    return None


def _extract_year_from_li(li) -> Optional[int]:
    """从 <li> 里抽取最可能的发表年份（1990-2099 的四位数）"""
    # 优先读 data-year
    if li.has_attr("data-year") and li["data-year"].isdigit():
        return int(li["data-year"])
    text = li.get_text(" ", strip=True)
    years = [int(y) for y in re.findall(r"\b(19[89]\d|20\d{2})\b", text)]
    if years:
        # 取最大的，因为发表年份通常是 li 里最晚的年份
        return max(years)
    return None


def parse_existing_entries(soup: BeautifulSoup) -> dict[str, list[ExistingEntry]]:
    """解析现有 HTML 里所有区块的所有 <li> 条目"""
    result: dict[str, list[ExistingEntry]] = {s: [] for s in SECTION_MAP}

    for section_name in SECTION_MAP:
        ol = find_section_ol(soup, section_name)
        if ol is None:
            continue
        for li in ol.find_all("li", recursive=True):
            title = _extract_title_from_li(li)
            if not title:
                # 没有可识别标题的 li（注释、空 li 等）跳过
                continue
            year = _extract_year_from_li(li)
            is_auto = li.has_attr("data-src") and li["data-src"].startswith("openalex:")
            entry = ExistingEntry(
                title_key=_normalize_title(title),
                year=year,
                raw_html=str(li),
                section=section_name,
                is_auto=is_auto,
            )
            result[section_name].append(entry)

    return result


def find_section_ol(soup: BeautifulSoup, section_name: str):
    """找到指定 h2 下方的 <ol>。如果只有 <ul> 没 <ol>，就地建一个。"""
    for header in soup.find_all("header"):
        h2 = header.find("h2")
        if h2 and h2.get_text(strip=True) == section_name:
            node = header
            for _ in range(10):
                node = node.find_next_sibling()
                if node is None:
                    break
                if not hasattr(node, "find"):
                    continue
                ol = node.find("ol") if node.name != "ol" else node
                if ol:
                    return ol
                if node.name == "ul":
                    new_ol = soup.new_tag("ol")
                    node.append(new_ol)
                    return new_ol
    return None


def dedupe_pub_versions(pubs: list[Pub]) -> list[Pub]:
    """OpenAlex 内部去重：同一论文的 preprint 和发表版本合并。
    
    规则：
    - 按 title_key 分组
    - 每组保留优先级最高的一个：非 preprint > preprint
    - 如果保留的是非 preprint 且同组有 preprint 带 arxiv_id，把 arxiv_id 合并过去
    """
    groups: dict[str, list[Pub]] = {}
    for p in pubs:
        groups.setdefault(p.title_key(), []).append(p)

    merged_count = 0
    result: list[Pub] = []
    for key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
            continue

        # 优先选非 preprint 的（如有多个，选年份最新的）
        non_preprints = [p for p in group if not p.is_preprint]
        preprints = [p for p in group if p.is_preprint]

        if non_preprints:
            chosen = max(non_preprints, key=lambda p: p.year or 0)
            # 从 preprint 版本补充 arxiv_id（如果发表版没有）
            if not chosen.arxiv_id:
                for pp in preprints:
                    if pp.arxiv_id:
                        chosen.arxiv_id = pp.arxiv_id
                        break
        else:
            chosen = max(preprints, key=lambda p: p.year or 0)

        result.append(chosen)
        merged_count += len(group) - 1

    if merged_count:
        print(f"[dedupe] 合并了 {merged_count} 个 preprint/重复版本")
    return result


def update_html(pubs: list[Pub], html_path: Path, dry_run: bool = False) -> None:
    """接管整个 HTML，合并现有条目 + OpenAlex 新论文，去重，按年份重排"""
    print(f"[html] 读取 {html_path}")
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    # ---- Step 1: OpenAlex 内部去重（preprint ↔ 已发表） ----
    pubs = dedupe_pub_versions(pubs)
    print(f"[dedupe] OpenAlex 去重后剩 {len(pubs)} 篇")

    # ---- Step 2: 解析现有 HTML ----
    existing_by_section = parse_existing_entries(soup)
    existing_total = sum(len(v) for v in existing_by_section.values())
    print(f"[html] 现有条目 {existing_total} 条")
    for s, entries in existing_by_section.items():
        n_auto = sum(1 for e in entries if e.is_auto)
        print(f"  [{s}] 共 {len(entries)}（自动 {n_auto}，手写 {len(entries) - n_auto}）")

    # ---- Step 3: 分类 OpenAlex pubs ----
    for p in pubs:
        p.category = categorize(p)

    # 所有现有 entries 按 title_key 建索引（用于查重）
    existing_by_key: dict[str, ExistingEntry] = {}
    for entries in existing_by_section.values():
        for e in entries:
            # 多个相同 title_key 时保留第一个（通常手写优先）
            if e.title_key not in existing_by_key:
                existing_by_key[e.title_key] = e

    # ---- Step 4: 构建每个 section 的最终条目列表 ----
    # final_by_section[section] = list of (year, raw_html)
    final_by_section: dict[str, list[tuple[Optional[int], str]]] = {s: [] for s in SECTION_MAP}

    # 先把现有条目都加进去（保留在原 section）
    # 自动条目会在下一步被 OpenAlex 数据覆盖更新
    for section_name, entries in existing_by_section.items():
        for e in entries:
            if not e.is_auto:
                # 手写条目：原封不动保留
                final_by_section[section_name].append((e.year, e.raw_html))

    # 处理 OpenAlex 条目
    stats = {"new": 0, "updated": 0, "kept_existing": 0}
    for pub in pubs:
        target_section = CATEGORY_TO_SECTION.get(pub.category, "Journal")

        if pub.title_key() in existing_by_key:
            existing = existing_by_key[pub.title_key()]
            if existing.is_auto:
                # 自动条目：用 OpenAlex 最新数据覆盖（放到新 section，可能与原不同）
                final_by_section[target_section].append((pub.year, render_li(pub)))
                stats["updated"] += 1
            else:
                # 手写条目：保留，但已在上面加过了，这里跳过
                stats["kept_existing"] += 1
        else:
            # 全新论文
            final_by_section[target_section].append((pub.year, render_li(pub)))
            stats["new"] += 1

    print(f"[merge] 新增 {stats['new']} / 更新 {stats['updated']} / 保留手写 {stats['kept_existing']}")

    # ---- Step 5: 按年份降序排序每个 section，然后重建 <ol> ----
    for section_name, items in final_by_section.items():
        items.sort(key=lambda x: (x[0] or 0), reverse=True)

        ol = find_section_ol(soup, section_name)
        if ol is None:
            print(f"[html] 警告：找不到区块 {section_name}，跳过")
            continue

        # 清空整个 ol
        ol.clear()

        # 重新插入，每个 li 前加换行和缩进
        indent = "\n\t\t\t\t\t\t\t\t\t\t\t\t"
        for year, li_html in items:
            ol.append(indent)
            li_soup = BeautifulSoup(li_html, "lxml")
            li_tag = li_soup.find("li")
            if li_tag:
                ol.append(li_tag)
        ol.append("\n\t\t\t\t\t\t\t\t\t\t\t")

        print(f"[html] [{section_name}] 重建完成，共 {len(items)} 条")

    # ---- Step 6: 插入"最后更新时间"标记 ----
    _update_last_updated_stamp(soup)

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

    # 清理旧备份，只保留最近 5 份
    backups = sorted(backup_dir.glob("publications.*.html"))
    for old in backups[:-5]:
        old.unlink()

    # 写回
    html_path.write_text(str(soup), encoding="utf-8")
    print(f"[html] 已更新 {html_path}")


def _update_last_updated_stamp(soup: BeautifulSoup) -> None:
    """在 publications.html 显眼位置放一个"最后更新时间"的小标注。
    查找 id="last-updated" 的元素；如果没找到，就在第一个 <article> 开头创建一个。
    """
    stamp_text = f"Last updated: {datetime.now().strftime('%Y-%m-%d')} (auto-synced from OpenAlex)"

    existing = soup.find(id="last-updated")
    if existing is not None:
        existing.clear()
        existing.string = stamp_text
        return

    # 没有，就创建一个并插到第一个 <article> 开头
    article = soup.find("article")
    if article is None:
        return
    p = soup.new_tag("p", id="last-updated",
                     style="font-size: 0.85em; color: #888; margin-bottom: 1em;")
    p.string = stamp_text
    # 插到 article 最前面
    article.insert(0, p)
    article.insert(1, "\n\t\t\t\t\t\t\t")


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