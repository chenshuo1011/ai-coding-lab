"""wordcount.py 的 pytest 单元测试：全部测试数据现场构造，不依赖真实文档。"""

import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape

import pytest

import wordcount

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _doc(body):
    """包一层最小的 word/document.xml。"""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    ).encode("utf-8")


def _p(*children):
    """拼一个 w:p 段落。"""
    return "<w:p>" + "".join(children) + "</w:p>"


def _r(text):
    """拼一个带文字的 w:r。"""
    return f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _tab():
    return "<w:tab/>"


def _br():
    return "<w:br/>"


def _cr():
    return "<w:cr/>"


def _write_docx(path, xml_bytes):
    """把 document.xml 写进一个最小 zip，返回路径。"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml_bytes)
    return path


def _make_docx(directory, name, text):
    """在临时目录里造一个只含一段文字的 docx。"""
    return _write_docx(directory / name, _doc(_p(_r(text))))


def test_extract_text_joins_runs_in_one_paragraph():
    # 测试同一段落内多个 run 的文字按顺序拼接
    xml = _doc(_p(_r("你"), _r("好"), _r("，"), _r("world")))
    assert wordcount.extract_text(xml) == "你好，world\n"


def test_extract_text_separates_paragraphs():
    # 测试多个段落之间用换行分隔，空段落保留为空行
    xml = _doc(_p(_r("第一段")) + _p() + _p(_r("第三段")))
    assert wordcount.extract_text(xml) == "第一段\n\n第三段\n"


def test_extract_text_handles_tab_br_and_cr():
    # 测试制表符转为 \t，手动换行和回车各产生一行
    xml = _doc(_p(_r("A"), _tab(), _r("B"), _br(), _r("C"), _cr(), _r("D")))
    assert wordcount.extract_text(xml) == "A\tB\nC\nD\n"


def test_extract_text_descends_into_table_cells():
    # 测试表格单元格里的段落文字也能按顺序取出
    table = (
        "<w:tbl><w:tr>"
        f"<w:tc>{_p(_r('甲'))}</w:tc>"
        f"<w:tc>{_p(_r('乙'))}</w:tc>"
        "</w:tr></w:tbl>"
    )
    assert wordcount.extract_text(_doc(table)) == "甲\n乙\n"


def test_extract_text_descends_into_nested_table():
    # 测试嵌套表格里的文字也能被统计且不重复
    inner = f"<w:tbl><w:tr><w:tc>{_p(_r('内层'))}</w:tc></w:tr></w:tbl>"
    outer = f"<w:tbl><w:tr><w:tc>{_p(_r('外层'))}{inner}</w:tc></w:tr></w:tbl>"
    text = wordcount.extract_text(_doc(outer))
    assert text.count("外层") == 1
    assert text.count("内层") == 1


def test_extract_text_reads_hyperlink_text():
    # 测试超链接容器里的文字也会被统计
    link = "<w:hyperlink><w:r><w:t>链接</w:t></w:r></w:hyperlink>"
    xml = _doc(_p(_r("前"), link, _r("后")))
    assert wordcount.extract_text(xml) == "前链接后\n"


def test_extract_text_counts_nested_textbox_once():
    # 测试文本框里嵌套的段落只统计一次，不会因递归重复
    textbox = f"<w:r><w:txbxContent>{_p(_r('框内文字'))}</w:txbxContent></w:r>"
    text = wordcount.extract_text(_doc(_p(textbox)))
    assert text.count("框内文字") == 1
    assert text.strip() == "框内文字"


def test_extract_text_ignores_deleted_and_field_code_text():
    # 测试删除修订 delText 和域代码 instrText 不计入正文
    xml = _doc(_p(
        _r("保留"),
        "<w:r><w:delText>删除</w:delText></w:r>",
        "<w:r><w:instrText>PAGE</w:instrText></w:r>",
    ))
    assert wordcount.extract_text(xml) == "保留\n"


def test_extract_text_empty_document_returns_empty_string():
    # 测试空文档返回空字符串
    assert wordcount.extract_text(_doc("")) == ""


def test_count_docx_counts_chars_without_whitespace(tmp_path):
    # 测试总字符数去掉空格、制表符和换行，汉字数只算汉字
    xml = _doc(_p(_r("中文 测试"), _tab(), _r("hello world 123")))
    path = _write_docx(tmp_path / "sample.docx", xml)
    assert wordcount.count_docx(path) == (17, 4, 1)


def test_count_docx_han_range_boundaries(tmp_path):
    # 测试常用汉字和扩展 A 区计入，扩展 B 区不在统计范围
    path = _write_docx(tmp_path / "range.docx", _doc(_p(_r("㐀䶿䷀一鿿𠀀"))))
    assert wordcount.count_docx(path) == (6, 4, 1)


def test_count_docx_empty_document(tmp_path):
    # 测试空文档统计为 0 字符、0 汉字、0 段落
    path = _write_docx(tmp_path / "empty.docx", _doc(""))
    assert wordcount.count_docx(path) == (0, 0, 0)


def test_count_docx_whitespace_only(tmp_path):
    # 测试只有空白字符时总字符数为 0，但仍有 1 个段落
    xml = _doc(_p(_r("   "), _tab(), _br(), _r("  "), _cr(), _r(" ")))
    path = _write_docx(tmp_path / "space.docx", xml)
    assert wordcount.count_docx(path) == (0, 0, 1)


def test_count_docx_counts_paragraphs_including_empty(tmp_path):
    # 测试段落数包含普通段落和空段落
    xml = _doc(_p(_r("甲")) + _p() + _p(_r("乙")))
    path = _write_docx(tmp_path / "paragraphs.docx", xml)
    assert wordcount.count_docx(path) == (2, 2, 3)


def test_count_docx_counts_table_paragraphs(tmp_path):
    # 测试表格单元格里的段落也计入段落数
    table = (
        "<w:tbl><w:tr>"
        f"<w:tc>{_p(_r('甲'))}</w:tc>"
        f"<w:tc>{_p(_r('乙'))}</w:tc>"
        "</w:tr></w:tbl>"
    )
    path = _write_docx(tmp_path / "table.docx", _doc(table))
    assert wordcount.count_docx(path) == (2, 2, 2)


def test_count_docx_counts_textbox_paragraphs(tmp_path):
    # 测试文本框内外的段落都计入段落数
    textbox = f"<w:r><w:txbxContent>{_p(_r('框内'))}</w:txbxContent></w:r>"
    path = _write_docx(tmp_path / "textbox.docx", _doc(_p(textbox)))
    assert wordcount.count_docx(path) == (2, 2, 2)


def test_count_docx_ignores_other_parts(tmp_path):
    # 测试只统计 word/document.xml，页眉等其他部件不参与
    path = tmp_path / "with-header.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", _doc(_p(_r("正文"))))
        zf.writestr("word/header1.xml", _doc(_p(_r("页眉"))))
    assert wordcount.count_docx(path) == (2, 2, 1)


def test_count_docx_missing_document_xml_raises_key_error(tmp_path):
    # 测试 zip 里没有 word/document.xml 时抛 KeyError
    path = tmp_path / "no-doc.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/other.xml", "<x/>")
    with pytest.raises(KeyError):
        wordcount.count_docx(path)


def test_count_docx_bad_zip_raises(tmp_path):
    # 测试不是 zip 的文件抛 BadZipFile
    path = tmp_path / "bad.docx"
    path.write_bytes(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        wordcount.count_docx(path)


def test_count_docx_missing_file_raises(tmp_path):
    # 测试文件不存在时抛 FileNotFoundError
    with pytest.raises(FileNotFoundError):
        wordcount.count_docx(tmp_path / "missing.docx")


def test_count_docx_directory_raises_os_error(tmp_path):
    # 测试传入目录时抛 OSError
    with pytest.raises(OSError):
        wordcount.count_docx(tmp_path)


def test_count_docx_malformed_xml_raises_parse_error(tmp_path):
    # 测试 document.xml 不是合法 XML 时抛 ParseError
    path = _write_docx(tmp_path / "broken.docx", b"<w:document>")
    with pytest.raises(ET.ParseError):
        wordcount.count_docx(path)


def test_display_width_counts_wide_and_narrow_chars():
    # 测试中文/全角字符占 2 格，英文占 1 格，空串为 0
    assert wordcount.display_width("") == 0
    assert wordcount.display_width("abc") == 3
    assert wordcount.display_width("中文") == 4
    assert wordcount.display_width("中aＢ") == 5


def test_pad_aligns_left_and_right_without_truncation():
    # 测试左/右对齐补空格，文字比目标宽度长时原样返回
    assert wordcount.pad("中文", 5) == "中文 "
    assert wordcount.pad("中文", 5, right=True) == " 中文"
    assert wordcount.pad("abcd", 2) == "abcd"
    assert wordcount.pad("abcd", 2, right=True) == "abcd"


def test_main_without_args_prints_usage(capsys):
    # 测试没有参数时打印帮助并返回 2
    assert wordcount.main([]) == 2
    out = capsys.readouterr().out
    assert "docx 字数统计小工具" in out
    assert "输出四列" in out


def test_main_prints_header_separator_and_row(tmp_path, capsys):
    # 测试单文件输出的四列表格结构和对齐宽度
    path = _make_docx(tmp_path, "报告.docx", "中文 test 123")
    assert wordcount.main([str(path)]) == 0
    header, separator, row = capsys.readouterr().out.splitlines()
    assert header.split() == ["文件名", "总字符数", "汉字数", "段落数"]
    assert separator == "-" * wordcount.display_width(header)
    assert row.startswith(str(path))
    assert row.split()[-3:] == ["9", "2", "1"]


def test_main_prints_paragraph_count(tmp_path, capsys):
    # 测试第四列输出段落数，空段落也计入
    xml = _doc(_p(_r("甲")) + _p() + _p(_r("乙")))
    path = _write_docx(tmp_path / "paragraphs.docx", xml)
    assert wordcount.main([str(path)]) == 0
    row = capsys.readouterr().out.splitlines()[2]
    assert row.split()[-3:] == ["2", "2", "3"]


def test_main_handles_multiple_files_in_order(tmp_path, capsys):
    # 测试多个文件参数按顺序输出多行
    first = _make_docx(tmp_path, "a.docx", "甲")
    second = _make_docx(tmp_path, "b.docx", "乙乙")
    assert wordcount.main([str(first), str(second)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 4
    assert str(first) in lines[2]
    assert str(second) in lines[3]
    assert lines[2].split()[-3:] == ["1", "1", "1"]
    assert lines[3].split()[-3:] == ["2", "2", "1"]


def test_main_expands_glob_pattern(tmp_path, capsys):
    # 测试通配符参数会展开成多个文件
    _make_docx(tmp_path, "a.docx", "甲")
    _make_docx(tmp_path, "b.docx", "乙")
    assert wordcount.main([str(tmp_path / "*.docx")]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 4


def test_main_keeps_going_when_one_file_is_missing(tmp_path, capsys):
    # 测试有文件缺失时仍输出有效文件，并返回 1
    good = _make_docx(tmp_path, "good.docx", "汉字")
    missing = tmp_path / "missing.docx"
    assert wordcount.main([str(good), str(missing)]) == 1
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 3
    assert "找不到文件" in captured.err
    assert str(missing) in captured.err


def test_main_reports_invalid_docx(tmp_path, capsys):
    # 测试坏文件只提示错误、不打印表格，并返回 1
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    assert wordcount.main([str(bad)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "不是有效的 docx" in captured.err


def test_main_reports_docx_without_document_xml(tmp_path, capsys):
    # 测试缺少 word/document.xml 的 zip 会被当作无效 docx
    path = tmp_path / "no-doc.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/other.xml", "<x/>")
    assert wordcount.main([str(path)]) == 1
    assert "不是有效的 docx" in capsys.readouterr().err


def test_main_reports_malformed_xml_and_continues(tmp_path, capsys):
    # 测试坏 XML 只提示错误并继续统计后面的有效文件
    bad = _write_docx(tmp_path / "broken-xml.docx", b"<w:document></w:document>")
    good = _make_docx(tmp_path, "good.docx", "正常")
    assert wordcount.main([str(bad), str(good)]) == 1
    captured = capsys.readouterr()
    assert "不是有效的 docx" in captured.err
    assert str(bad) in captured.err
    assert str(good) in captured.out
    assert len(captured.out.splitlines()) == 3


def test_main_reports_directory_as_invalid(tmp_path, capsys):
    # 测试传入目录时提示不是有效 docx
    assert wordcount.main([str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "不是有效的 docx" in captured.err


def test_main_keeps_argument_when_glob_has_no_match(tmp_path, capsys, monkeypatch):
    # 测试 glob 没匹配时保留原参数并报找不到文件
    monkeypatch.setattr(wordcount.glob, "glob", lambda pattern: [])
    missing = str(tmp_path / "missing.docx")
    assert wordcount.main([missing]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "找不到文件" in captured.err
    assert missing in captured.err
