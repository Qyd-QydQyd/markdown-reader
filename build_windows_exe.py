from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller 未安装。请先执行: pip install pyinstaller")
        return 1

    project_dir = Path(__file__).resolve().parent
    spec_file = project_dir / "paper_reader_windows.spec"
    if not spec_file.exists():
        print(f"未找到 spec 文件: {spec_file}")
        return 1

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_file)],
        cwd=str(project_dir.parent),
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
