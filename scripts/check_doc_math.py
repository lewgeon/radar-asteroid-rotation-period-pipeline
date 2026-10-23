#!/usr/bin/env python
"""检查 Markdown 行间公式（``$$``）是否为围栏写法。

背景：DSH 侧边栏的文件预览用 micromark + mdast-util-math 解析 Markdown，
它把 ``$$`` 当作**围栏块**（与 ``` 代码块同级），要求

* 开栏 ``$$`` 独占一行；
* 闭栏 ``$$`` 独占一行。

写成 ``$$公式$$`` 会被降级为**行内公式**（含 ``\\tag`` 时 KaTeX 直接报错，
渲染成红字源码）；写成 ``$$公式``（开栏行带内容）则内容被当作 fence meta，
解析器找不到合法闭栏而**一路吞到文件末尾**。Typora 对这两种写法都宽容，
因此本地预览正常、侧边栏却渲染错。

本脚本用纯标准库实现同一不变式：**文件中每个 ``$$`` 都必须独占一行**。
满足它时，公式块的开栏/闭栏必然成对且合法。

用法::

    python scripts/check_doc_math.py                 # 扫描仓库内当前版本文档
    python scripts/check_doc_math.py docs/4.3        # 只扫描指定目录或文件

冻结的版本快照（docs/4.1、docs/4.2）按仓库约定不再回改，脚本只汇总、不计入退出码。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIR_NAMES = {".git", "node_modules", "tmp", "outputs", ".pytest_cache", "__pycache__"}
FROZEN_PREFIXES = ("docs/4.1/", "docs/4.2/")
FENCE = "$$"


def collect(targets: list[str]) -> list[Path]:
    if targets:
        found: list[Path] = []
        for item in targets:
            path = Path(item)
            if not path.is_absolute():
                path = ROOT / path
            if path.is_dir():
                found.extend(sorted(path.rglob("*.md")))
            elif path.is_file():
                found.append(path)
        return found
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not (SKIP_DIR_NAMES & set(path.relative_to(ROOT).parts))
    )


def inspect(path: Path) -> tuple[list[str], int]:
    """返回 (违规描述列表, 完整公式块数)。"""

    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    delimiters = 0
    in_fence = False
    fence_marker = ""
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence, fence_marker = False, ""
            continue
        if in_fence:
            continue
        # 行内代码里的 $$ 只是举例（例如规范里写 `$$...$$`），不是公式定界符。
        candidate = re.sub(r"`[^`]*`", "", line)
        occurrences = candidate.count(FENCE)
        if occurrences == 0:
            continue
        delimiters += occurrences
        if candidate.strip() != FENCE:
            problems.append(
                f"{path.relative_to(ROOT)}:{number}: '$$' 未独占一行 -> {candidate.strip()[:70]}"
            )
    if delimiters % 2 != 0:
        problems.append(f"{path.relative_to(ROOT)}: '$$' 出现 {delimiters} 次（奇数），围栏未配对")
    return problems, delimiters // 2


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Markdown 行间公式围栏写法")
    parser.add_argument("targets", nargs="*", help="待检查的文件或目录（缺省扫描整个仓库）")
    args = parser.parse_args()

    current: list[str] = []
    frozen: list[str] = []
    blocks = 0
    checked = 0
    for path in collect(args.targets):
        rel = path.relative_to(ROOT).as_posix()
        problems, count = inspect(path)
        if count or problems:
            checked += 1
        blocks += count
        if rel.startswith(FROZEN_PREFIXES):
            frozen.extend(problems)
        else:
            current.extend(problems)

    print(f"扫描 {checked} 个含行间公式的文档，识别出 {blocks} 个完整公式块。")
    if current:
        print(f"\n当前版本文档违规 {len(current)} 处：")
        for item in current:
            print("  ! " + item)
    else:
        print("当前版本文档：全部合规。")
    if frozen:
        print(f"\n冻结快照（docs/4.1、docs/4.2，按约定不回改）违规 {len(frozen)} 处：")
        for item in frozen[:10]:
            print("  - " + item)
        if len(frozen) > 10:
            print(f"  - ...（其余 {len(frozen) - 10} 处省略）")
    return 1 if current else 0


if __name__ == "__main__":
    sys.exit(main())
