"""
变异测试（Mutation Testing）

原理：把被测代码故意改坏一小处，然后跑测试。
  - 测试失败  -> 这个变异"被杀死"，说明测试能发现这类错误
  - 测试仍通过 -> 这个变异"存活"，说明测试根本没覆盖到这一处

一个测试套件如果连故意改坏的代码都发现不了，它就是形同虚设。

用法（在 D:/AI-Study/tools 目录下）：
    ..\\.venv\\Scripts\\python.exe ..\\ai-coding-lab\\mutation_test.py test_wordcount.py

参数是测试文件的路径（相对 tools 目录或绝对路径都行）。
运行前请确保测试本来是全部通过的，否则结论没意义。
"""

import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"
TARGET = TOOLS / "wordcount.py"
PY = Path(r"D:\AI-Study\.venv\Scripts\python.exe")

# (编号, 说明, 原文, 改坏后)
MUTATIONS = [
    (
        "M1",
        "字符数不再去掉空格",
        '    return len(re.sub(r"\\s+", "", text)), len(HAN_RE.findall(text))',
        '    return len(text), len(HAN_RE.findall(text))',
    ),
    (
        "M2",
        "汉字正则去掉生僻字区间",
        'HAN_RE = re.compile(r"[\\u3400-\\u4dbf\\u4e00-\\u9fff]")',
        'HAN_RE = re.compile(r"[\\u4e00-\\u9fff]")',
    ),
    (
        "M3",
        "不再递归进表格 / 文本框",
        "            else:\n                walk(child)           # 表格、超链接、文本框等容器，继续往里钻",
        "            else:\n                pass",
    ),
    (
        "M4",
        "文件不存在的异常处理失效",
        "        except FileNotFoundError:",
        "        except ZeroDivisionError:",
    ),
    (
        "M5",
        "通配符不再展开",
        "        paths.extend(glob.glob(arg) or [arg])",
        "        paths.append(arg)",
    ),
]


def run_tests(test_path: Path) -> tuple[bool, str]:
    """跑测试，返回 (是否通过, 输出尾部)"""
    r = subprocess.run(
        [str(PY), "-m", "pytest", str(test_path), "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(TOOLS), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, out.strip().split("\n")[-1][:60]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    test_file = Path(sys.argv[1])
    if not test_file.is_absolute():
        test_file = TOOLS / test_file
    if not test_file.exists():
        print(f"找不到测试文件: {test_file}")
        return 2
    if not TARGET.exists():
        print(f"找不到被测文件: {TARGET}")
        return 2

    original = TARGET.read_text(encoding="utf-8")
    backup = TARGET.with_suffix(".py.bak")
    shutil.copy2(TARGET, backup)

    try:
        print("=" * 64)
        print("第 0 步：原始代码跑测试（必须通过，否则后面没意义）")
        print("=" * 64)
        ok, tail = run_tests(test_file)
        print(f"  {'通过' if ok else '失败'}  |  {tail}")
        if not ok:
            print("\n原始代码就没通过测试，先修测试，再来做变异。")
            return 1

        print()
        print("=" * 64)
        print("第 1 步：逐个改坏代码，看测试能不能发现")
        print("=" * 64)
        print(f"{'编号':<6}{'改坏了什么':<26}{'测试反应':<12}{'结果'}")
        print("-" * 64)

        killed = 0
        survived = []
        for mid, desc, old, new in MUTATIONS:
            if old not in original:
                print(f"{mid:<6}{desc:<26}{'(找不到锚点，跳过)':<12}")
                continue
            TARGET.write_text(original.replace(old, new, 1), encoding="utf-8")
            ok, _ = run_tests(test_file)
            shutil.copy2(backup, TARGET)   # 立刻恢复，避免下一个变异叠加

            if ok:
                print(f"{mid:<6}{desc:<26}{'仍然通过':<12}存活 ❌")
                survived.append((mid, desc))
            else:
                print(f"{mid:<6}{desc:<26}{'失败/报错':<12}杀死 ✅")
                killed += 1

        total = killed + len(survived)
        print("-" * 64)
        print(f"被杀死 {killed}/{total} 个变异")
        print()

        if not survived:
            print("结论：这套测试是有效的——任意改坏一处它都能发现。")
        elif killed == 0:
            print("结论：这套测试基本无效。改坏了都不报错，说明断言可能只是 '不是 None' 之类。")
        else:
            print("结论：测试部分有效，但有盲区。以下改动它发现不了：")
            for mid, desc in survived:
                print(f"  - {mid} {desc}")
        return 0
    finally:
        shutil.copy2(backup, TARGET)
        backup.unlink(missing_ok=True)
        print("\n（wordcount.py 已恢复原样）")


if __name__ == "__main__":
    raise SystemExit(main())
