from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Tk, filedialog


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1]:
        print(Path(sys.argv[1]).expanduser())
        return

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askopenfilename(
        title="选择论文 Markdown 文件",
        filetypes=[
            ("Markdown", "*.md *.markdown *.txt"),
            ("All Files", "*.*"),
        ],
    )
    root.destroy()

    if selected:
        print(Path(selected).expanduser())


if __name__ == "__main__":
    main()
