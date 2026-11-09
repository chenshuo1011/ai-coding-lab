"""
docx 字数统计小工具 —— 用 python-docx 实现，功能和 wordcount.py 一致。

统计范围：正文里所有 w:t 文字，包括表格（合并单元格、嵌套表格）、文本框、
内容控件（如目录）等；页眉页脚、脚注、批注不计，和 wordcount.py 只读
word/document.xml 的口径相同。

运行方式（在 D:/AI-Study/tools 目录下）：
    ../.venv/Scripts/python.exe wordcount_docx.py 报告.docx
    ../.venv/Scripts/python.exe wordcount_docx.py 一.docx 二.docx "D:/某目录/*.docx"

输出三列：文件名、总字符数（不含空格）、纯中文汉字数。
"""

import glob
import os
import re
import sys
import unicodedata
import zipfile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn

# 汉字区间：4E00-9FFF 是常用汉字，3400-4DBF 是扩展 A 区（生僻字）
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
W_T = qn("w:t")   # Word XML 里的文字节点


def _collect_paragraph(paragraph, chunks, counted):
    """收集一个段落的全部 w:t；记下节点，避免后面兜底扫描重复统计。"""
    # 用底层 w:p 而不是 paragraph.text：只认 w:t，和 wordcount.py 完全同口径
    for node in paragraph._p.iter(W_T):
        chunks.append(node.text or ""); counted.add(node)


def _collect_table(table, chunks, counted):
    """递归收集表格文字；合并单元格会在 row.cells 里重复，按 w:tc 去重。"""
    seen_cells = set()
    for row in table.rows:
        for cell in row.cells:
            if cell._tc in seen_cells: continue
            seen_cells.add(cell._tc)
            for paragraph in cell.paragraphs: _collect_paragraph(paragraph, chunks, counted)
            for nested in cell.tables: _collect_table(nested, chunks, counted)  # 嵌套表格


def extract_text(document):
    """取出整份文档正文的纯文本。"""
    chunks, counted = [], set()
    # 第一遍：走 python-docx 对象模型，正文段落 + 顶层表格（表格内部递归）
    for paragraph in document.paragraphs: _collect_paragraph(paragraph, chunks, counted)
    for table in document.tables: _collect_table(table, chunks, counted)
    # 第二遍：补对象模型漏掉的 w:t（文本框、内容控件、修订插入等），节点集合防重复
    chunks += [n.text or "" for n in document.element.iter(W_T) if n not in counted]
    return "\n".join(chunks)


def count_docx(path):
    """统计单个 docx，返回 (不含空格的字符数, 汉字数)。"""
    text = extract_text(Document(path))
    # \s 覆盖空格、制表符、换行；全去掉，就是 Word 里"字符数(不计空格)"的口径
    return len(re.sub(r"\s+", "", text)), len(HAN_RE.findall(text))


def display_width(text):
    """按终端显示宽度算长度：中文占 2 格，英文占 1 格，这样表格才对齐。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text, w, right=False):
    """补空格对齐：right=True 右对齐（数字列），否则左对齐（文件名列）。"""
    space = " " * max(0, w - display_width(text))
    return space + text if right else text + space


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    # 把参数展开成真实文件列表；通配符没匹配到就原样保留，好在下面报"找不到文件"
    paths = []
    for arg in argv:
        paths.extend(glob.glob(arg) or [arg])

    rows, failed = [], 0
    for path in paths:
        try:
            chars, hans = count_docx(path)
            rows.append((path, chars, hans))
        except (FileNotFoundError, PackageNotFoundError):
            # 不存在 -> 找不到文件；存在但打不开（目录、缺 document.xml 等）-> 无效 docx
            if os.path.exists(path):
                print(f"[跳过] 不是有效的 docx（或读不了，比如传了目录/缺少 document.xml）：{path}", file=sys.stderr)
            else:
                print(f"[跳过] 找不到文件：{path}", file=sys.stderr)
            failed += 1
        except (zipfile.BadZipFile, KeyError, OSError):
            print(f"[跳过] 不是有效的 docx（或读不了，比如传了目录/缺少 document.xml）：{path}", file=sys.stderr)
            failed += 1

    if not rows: return 1
    # 按内容和表头算出每列宽度，打印成规整的三列表格
    # 元组第二位是这一列在 rows 里的下标：0 文件名、1 总字符数、2 汉字数
    cols = [("文件名", 0), ("总字符数", 1), ("汉字数", 2)]
    widths = [max([display_width(h)] + [display_width(str(r[i])) for r in rows]) for h, i in cols]
    header = "  ".join(pad(h, w, right=(i > 0)) for (h, i), w in zip(cols, widths))
    print(header)
    print("-" * display_width(header))
    for path, chars, hans in rows:
        cells = [path, str(chars), str(hans)]
        print("  ".join(pad(c, w, right=(j > 0)) for j, (c, w) in enumerate(zip(cells, widths))))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
