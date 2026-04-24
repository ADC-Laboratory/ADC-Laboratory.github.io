"""
ADC Lab Publication Updater - Configuration

数据源：OpenAlex (https://openalex.org)
设计原则：尽量用 OpenAlex 的结构化字段识别，避免硬编码字符串。
"""

# ============ 1. 作者身份 ============

# PI 的 OpenAlex Author ID（推荐方式，最精确）
# 查找：https://openalex.org/works?filter=authorships.author.id:A5xxx 里的 A5xxx
OPENALEX_AUTHOR_ID = "A5067909017"   # Dr. Jingliang Duan

# 备选 1：ORCID（如果 Dr. Duan 有 ORCID）
AUTHOR_ORCID = ""

# 备选 2：名字搜索（没 ID 时自动用）
AUTHOR_NAME = "Jingliang Duan"


# ============ 2. 加粗哪些作者（用 OpenAlex ID，而非名字拼写）============

# OpenAlex 每个作者有唯一 ID，用它匹配比用 "J Duan" / "Jingliang Duan" 这种
# 字符串可靠得多。脚本每次跑会打印 top co-authors 列表，从日志里挑 ID
# 复制到这里即可。
BOLD_AUTHOR_IDS = [
    "A5067909017",   # Jingliang Duan (PI)
    # 往这里加实验室成员的 OpenAlex author ID —— 跑一次脚本看日志 [coauthors] 部分
]


# ============ 3. 论文过滤（针对 OpenAlex 作者消歧错误）============

# 最早年份。段老师学术生涯从约 2017 年开始，设 2016 安全。
MIN_YEAR = 2016

# 机构过滤：开启后，要求论文里 Dr. Duan 对应的 authorship 关联的机构，
# 必须是他"历史机构"之一。脚本会自动从 OpenAlex author 对象的 affiliations
# 字段拉取历史机构（USTB / Tsinghua / NUS / UC Berkeley 等都会自动包含），
# 不需要手动维护关键词白名单。
REQUIRE_INSTITUTION_MATCH = True

# OpenAlex work ID 黑名单（当自动过滤没拦住某篇时用）
EXCLUDE_WORK_IDS = []

# 标题关键词黑名单（命中即过滤，大小写不敏感）
EXCLUDE_TITLE_KEYWORDS = []


# ============ 4. OpenAlex 请求配置 ============

# email 会进入 polite pool，响应更快
OPENALEX_EMAIL = "duanjl15@163.com"

# 抓取上限
MAX_PUBLICATIONS = 500

# 请求间隔（OpenAlex 不限速，0.2s 足够）
REQUEST_DELAY = 0.2


# ============ 5. 分类兜底规则 ============
# 分类优先级（前 3 级是通用 OpenAlex 字段，很少走到第 4 级）：
#   1. is_preprint → arxiv
#   2. OpenAlex work.type / source.type（journal-article / proceedings-article / book-chapter）
#   3. DOI pattern（IEEE 会议/期刊 DOI 有固定格式）
#   4. venue 字符串关键词匹配（以下规则，最终兜底）
CATEGORY_RULES = [
    ("arxiv",         ["arxiv"]),
    ("book_chapter",  ["book", "chapter", "ebook"]),
    ("conference",    ["conference", "proceedings", "workshop", "symposium"]),
    ("journal",       ["journal", "transactions", "letters", "magazine"]),
]

DEFAULT_CATEGORY = "journal"


# ============ 6. 文件路径 ============

PUBLICATIONS_HTML = "publications.html"
BACKUP_DIR = "tool/backups"
CACHE_FILE = "tool/cache/publications.json"


# ============ 7. 代理配置（GitHub Actions 不需要）============

USE_PROXY = False
PROXY_HTTP = "http://127.0.0.1:7890"
PROXY_HTTPS = "http://127.0.0.1:7890"