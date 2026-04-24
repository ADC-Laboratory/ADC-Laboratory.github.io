"""
一次性清理脚本
============

清掉旧版脚本在 publications.html 里留下的自动区标记和条目。
在用新版脚本前跑一次，让 HTML 回到"干净初始状态"。

用法:
    python tool/cleanup_old_auto_blocks.py

清理规则:
  1. 删除所有 <!-- AUTO-SCHOLAR-BEGIN --> 到 <!-- AUTO-SCHOLAR-END --> 之间的内容
  2. 删除这两个注释标记本身
  3. 现有的手写条目全部保留不动

运行前会自动备份到 tool/backups/。
"""

from __future__ import annotations
import shutil
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, Comment

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parent
HTML_PATH = REPO_ROOT / "publications.html"
BACKUP_DIR = _HERE / "backups"


def main():
    if not HTML_PATH.exists():
        print(f"错误：找不到 {HTML_PATH}")
        sys.exit(1)

    # 备份
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"publications.{stamp}.html"
    shutil.copy2(HTML_PATH, backup_path)
    print(f"[backup] 已备份原文件到 {backup_path}")

    html = HTML_PATH.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    # 找到所有 BEGIN/END 注释对
    begin_marks = []
    end_marks = []
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        text = c.string.strip() if c.string else ""
        if text == "AUTO-SCHOLAR-BEGIN":
            begin_marks.append(c)
        elif text == "AUTO-SCHOLAR-END":
            end_marks.append(c)

    print(f"[scan] 找到 {len(begin_marks)} 对 AUTO-SCHOLAR 标记")

    removed = 0
    for begin, end in zip(begin_marks, end_marks):
        # 收集 begin 到 end 之间的所有节点（不含 begin/end 本身）
        nodes_to_remove = []
        node = begin.next_sibling
        while node is not None and node is not end:
            nodes_to_remove.append(node)
            node = node.next_sibling
        for n in nodes_to_remove:
            n.extract()
            removed += 1
        begin.extract()
        end.extract()

    print(f"[clean] 删除了 {removed} 个节点（包括 li、换行、空格等）")

    # 写回
    HTML_PATH.write_text(str(soup), encoding="utf-8")
    print(f"[done] 已清理 {HTML_PATH}")
    print(f"[tip] 现在可以跑 `python tool/fetch_scholar.py` 重新生成了")


if __name__ == "__main__":
    main()