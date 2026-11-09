"""
docx 字数统计小工具 —— 只用标准库，不装任何第三方包。

原理：.docx 本质是个 zip 压缩包，正文都在 word/document.xml 里。
      用 zipfile 读出这个 XML，再用 xml.etree 解析，按顺序把每个
      <w:t>（文字片段）取出来拼成纯文本，然后对纯文本做统计。

运行方式（在 D:\\AI-Study\\tools 目录下）：
    ..\\.venv\\Scripts\\python.exe wordcount.py 报告.docx
    ..\\.venv\\Scripts\\python.exe wordcount.py 一.docx 二.docx 三.docx
    ..\\.venv\\Scripts\\python.exe wordcount.py "D:\\某目录\\*.docx"   （支持通配符）

输出四列：文件名、总字符数（不含空格）、纯中文汉字数、段落数。
"""

import glob
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

# Word 的 XML 里标签都带这个命名空间，取标签时必须带上
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
P, T, TAB = NS + "p", NS + "t", NS + "tab"   # 段落 / 文字 / 制表符
BR, CR = NS + "br", NS + "cr"                 # 手动换行 / 回车

# 汉字区间：4E00-9FFF 是常用汉字，3400-4DBF 是扩展 A 区（生僻字）
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

def _extract_text_and_paragraphs(xml_bytes):
    """解析 document.xml，返回 (纯文本, 段落数)。"""
    root = ET.fromstring(xml_bytes)
    lines, buf = [], []   # lines 是已收尾的段落，buf 是当前段落缓冲
    paragraphs = 0        # 每个 <w:p> 算一段，含空段落、表格和文本框里的段落

    def walk(node):
        # 不能简单用 node.iter()：文本框里的段落会嵌套在段落里，那样会被算两遍。
        # 自己递归一层层往下走，顺序和重复问题都不会有。
        nonlocal buf, paragraphs
        for child in node:
            tag = child.tag
            if tag == P:
                paragraphs += 1
                buf = []              # 开新段落
                walk(child)           # 处理段落内部
                lines.append("".join(buf))
                buf = []
            elif tag == T:
                buf.append(child.text or "")
            elif tag == TAB:
                buf.append("\t")
            elif tag in (BR, CR):
                lines.append("".join(buf))
                buf = []
            else:
                walk(child)           # 表格、超链接、文本框等容器，继续往里钻

    walk(root)
    lines.append("".join(buf))
    return "\n".join(lines), paragraphs

def extract_text(xml_bytes):
    """从 document.xml 的字节里按顺序取出纯文本，段落之间用换行分隔。"""
    return _extract_text_and_paragraphs(xml_bytes)[0]

def count_docx(path):
    """统计单个 docx，返回 (不含空格的字符数, 汉字数, 段落数)。"""
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("word/document.xml")
    text, paragraphs = _extract_text_and_paragraphs(xml_bytes)
    # \s 覆盖空格、制表符、换行；全去掉，就是 Word 里"字符数(不计空格)"的口径
    return len(re.sub(r"\s+", "", text)), len(HAN_RE.findall(text)), paragraphs

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
            chars, hans, paragraphs = count_docx(path)
            rows.append((path, chars, hans, paragraphs))
        except FileNotFoundError:
            print(f"[跳过] 找不到文件：{path}", file=sys.stderr)
            failed += 1
        except (zipfile.BadZipFile, KeyError, OSError, ET.ParseError):
            print(f"[跳过] 不是有效的 docx（或读不了，比如传了目录/缺少 document.xml）：{path}", file=sys.stderr)
            failed += 1

    if not rows:
        return 1

    # 按内容和表头算出每列宽度，打印成规整的四列表格
    # 元组第二位是这一列在 rows 里的下标：0 文件名、1 总字符数、2 汉字数、3 段落数
    cols = [("文件名", 0), ("总字符数", 1), ("汉字数", 2), ("段落数", 3)]
    widths = [max([display_width(h)] + [display_width(str(r[i])) for r in rows]) for h, i in cols]

    header = "  ".join(pad(h, w, right=(i > 0)) for (h, i), w in zip(cols, widths))
    print(header)
    print("-" * display_width(header))
    for path, chars, hans, paragraphs in rows:
        cells = [path, str(chars), str(hans), str(paragraphs)]
        print("  ".join(pad(c, w, right=(j > 0)) for j, (c, w) in enumerate(zip(cells, widths))))

    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
