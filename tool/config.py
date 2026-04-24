"""
ADC Lab Publication Updater - Configuration

数据源：OpenAlex (https://openalex.org)
- 免费、开放、不限速、不封 IP
- 有 2.86 亿篇学术作品，覆盖 Google Scholar 的绝大部分内容
- 非常适合 GitHub Actions 运行
"""

# ============ 作者身份（三种任选其一，推荐方式 1）============

# 方式 1：OpenAlex Author ID（最精确）
# 查找方法：
#   打开 https://api.openalex.org/authors?search=Jingliang%20Duan
#   或访问 https://openalex.org 搜 "Jingliang Duan"，URL 里的 A5xxxxxxxxx 就是 ID
# 首次运行脚本会自动尝试搜索，可以把日志里挑选出的 ID 填回这里固化下来
OPENALEX_AUTHOR_ID = "A5067909017"   # Dr. Jingliang Duan

# 方式 2：ORCID（如果 Dr. Duan 有 ORCID，也非常精确）
AUTHOR_ORCID = ""   # 例如 "0000-0002-1234-5678"

# 方式 3：按名字+机构搜索（没有 ID 时自动用这个）
AUTHOR_NAME = "Jingliang Duan"
# 机构关键词：用于在多个同名作者中挑出正确的那个
# 任一关键词命中，匹配分就 +100
AUTHOR_INSTITUTION_HINTS = [
    "University of Science and Technology Beijing",
    "USTB",
    "Tsinghua",              # 博士阶段在清华
    "Beijing Institute",
]

# ============ OpenAlex 礼貌池配置 ============
# 在请求中带上 email 会进入 "polite pool"，响应更快。
# 可以留空，但填了更好，建议填实验室联系邮箱
OPENALEX_EMAIL = "duanjl15@163.com"

# ============ 旧字段（保留兼容，不会再用）============
SCHOLAR_USER_ID = "jaofXZIAAAAJ"

# ============ 抓取控制 ============
MAX_PUBLICATIONS = 500

# ============ 作者名字加粗规则 ============
# 这些名字出现在作者列表中时会被自动加粗 <b>...</b>
# OpenAlex 返回的作者名通常是完整形式，脚本会自动压缩成 "J. Duan" 风格
# 所以这里两种写法都加上
BOLD_AUTHORS = [
    # PI
    "Jingliang Duan",
    "J Duan",
    "J. Duan",
    "段京良",
    # 实验室学生/成员 —— 按需增删
    "Haoqi Yan",
    "H Yan",
    "H. Yan",
    "Haoyuan Xu",
    "H Xu",
    "H. Xu",
    "Liming Xiao",
    "L Xiao",
    "L. Xiao",
    "Liangfa Chen",
    "L Chen",
    "L. Chen",
    "Chunxuan Jiao",
    "C Jiao",
    "C. Jiao",
    "陈良发",
    "焦春绚",
]

# ============ 论文分类关键词 ============
CATEGORY_RULES = [
    ("arxiv",         ["arxiv", "arxiv preprint"]),
    ("book_chapter",  ["chapter", "book chapter", "in book:"]),
    ("conference",    [
        "conference", "proceedings", "workshop", "symposium",
        "iccv", "cvpr", "icml", "neurips", "nips", "aaai", "ijcai", "iclr",
        "acc", "cdc", "icra", "iros", "iv symposium", "itsc", "icus",
    ]),
    ("journal",       ["journal", "transactions", "letters", "magazine",
                        "ieee trans", "nature", "science"]),
]

DEFAULT_CATEGORY = "journal"

# ============ 网站文件路径 ============
PUBLICATIONS_HTML = "publications.html"
BACKUP_DIR = "tool/backups"
CACHE_FILE = "tool/cache/publications.json"

# ============ 抓取行为 ============
REQUEST_DELAY = 0.2   # OpenAlex 允许较快，0.2s 足够
RECENT_YEARS_ONLY = 0

# ============ 代理配置（GitHub Actions 不需要）============
USE_PROXY = False
PROXY_HTTP = "http://127.0.0.1:7890"
PROXY_HTTPS = "http://127.0.0.1:7890"
