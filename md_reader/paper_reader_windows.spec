# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path.cwd() / "md_reader"
icon_path = project_dir / "AppIcon.ico"

datas = [
    (str(project_dir / "server.py"), "."),
    (str(project_dir / "select_markdown.py"), "."),
]

a = Analysis(
    [str(project_dir / "paper_reader_windows.pyw")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PaperReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
