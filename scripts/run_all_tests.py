"""Run root, observation, echo, and inversion tests in the pytorch conda env."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITES = (
    ("root", ROOT, ["-m", "pytest", "-q", "tests"]),
    ("observation", ROOT, ["-m", "pytest", "-q", "observation/tests"]),
    ("echo", ROOT / "echo", ["-m", "pytest", "-q", "tests"]),
    ("inversion", ROOT, ["-m", "pytest", "-q", "inversion/tests"]),
)


def _python_cmd():
    return ["conda", "run", "-n", "pytorch", "--no-capture-output", "python"]


def main() -> int:
    failures = []
    for name, cwd, args in SUITES:
        command = _python_cmd() + args
        print(f"\n== {name} ==", flush=True)
        print(" ".join(command), flush=True)
        completed = subprocess.run(command, cwd=str(cwd), check=False)
        if completed.returncode != 0:
            failures.append((name, completed.returncode))
    if failures:
        print("\n失败：", flush=True)
        for name, code in failures:
            print(f"  {name}: 退出码 {code}", flush=True)
        return 1
    print("\n四组测试全部通过。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
