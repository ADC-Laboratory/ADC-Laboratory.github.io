"""
ADC Lab Publication Updater - Configuration

修改这里的配置来适配你的需求。
"""

# ============ Google Scholar 配置 ============

# Dr. Jingliang Duan 的 Google Scholar user ID
# 从 URL https://scholar.google.com.hk/citations?user=jaofXZIAAAAJ 提取
SCHOLAR_USER_ID = "jaofXZIAAAAJ"

# 最多抓取多少篇论文（按 scholar 页面顺序，默认按年份新到旧）
MAX_PUBLICATIONS = 200

# ============ 作者名字加粗规则 ============
# 这些名字出现在作者列表中时会被自动加粗 <b>...</b>
# 注意大小写不敏感，按名字长度降序匹配避免误伤
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
# 根据 venue（发表场所）把论文分到四个区块
# 匹配从上到下，命中第一条就归类
CATEGORY_RULES = [
    # (类别名, venue 里出现任一关键词就归到这一类)
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

# 未命中任何类别时的默认归属
DEFAULT_CATEGORY = "journal"

# ============ 网站文件路径 ============
# 相对于仓库根目录
PUBLICATIONS_HTML = "publications.html"

# 备份文件保存目录
BACKUP_DIR = "tool/backups"

# 缓存文件（保存已抓取的论文，避免每次全量重抓）
CACHE_FILE = "tool/cache/publications.json"

# ============ 抓取行为 ============
# Google Scholar 对频繁请求会封 IP，设置延迟（秒）
REQUEST_DELAY = 2.0

# 只抓取最近 N 年的论文（0 表示全部），用于首次抓取后做增量
RECENT_YEARS_ONLY = 0

# ============ 代理配置（仅本地运行需要）============
# GitHub Actions 上跑不需要设置这些
# 在大陆本地跑时，改成你的代理端口
# 支持 http / socks5
USE_PROXY = False
PROXY_HTTP = "http://127.0.0.1:7890"     # Clash 默认
PROXY_HTTPS = "http://127.0.0.1:7890"
# 如果是 SOCKS5：PROXY_HTTP = "socks5://127.0.0.1:7891"
