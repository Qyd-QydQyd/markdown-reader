# Paper Reader 使用说明

Paper Reader 是一个用于阅读 Markdown 文档的小工具，适合论文、笔记和带图片、表格、公式的文档。

支持的文件类型：

- `.md`
- `.markdown`
- `.txt`

支持的主要功能：

- 打开本地 Markdown 文档
- 显示图片
- 显示表格
- 显示 LaTeX 公式
- 优化目录显示
- 优化参考文献显示
- 导出 PDF

---

## 1. 最简单的使用方法

### macOS

直接打开：

- `Paper Reader.app`

或者双击：

- `Markdown Reader.command`

打开后：

1. 选择要阅读的 `.md` 文件
2. 浏览器会自动打开阅读页面
3. 需要导出 PDF 时，点击页面里的 `导出 PDF`

### Windows

如果已经打包好程序，直接双击：

- `PaperReader.exe`

如果暂时还没有 `.exe`，可以先双击：

- `launch_reader.bat`

打开后：

1. 选择要阅读的 `.md` 文件
2. 浏览器会自动打开阅读页面
3. 需要导出 PDF 时，点击页面里的 `导出 PDF`

---

## 2. 第一次使用前的准备

你至少需要有：

- Python 3.9 或更高版本
- 一个要阅读的 Markdown 文件

检查 Python 是否可用：

- macOS：`python3 --version`
- Windows：`python --version`

---

## 3. 手动启动方法

如果双击打不开，可以在项目根目录手动运行。

```bash
python3 launch_reader.py
```

如果想直接指定文件：

```bash
python3 launch_reader.py "/absolute/path/to/your-file.md"
```

Windows 里也可以写成：

```bash
python launch_reader.py "C:\\path\\to\\your-file.md"
```

打开后，浏览器地址通常是：

```text
http://read-md.localhost:8765
```

Windows 打包版默认使用：

```text
http://localhost:8765
```

---

## 4. Windows 打包成 exe

在项目根目录执行：

### 第一步

安装 PyInstaller：

```bash
pip install pyinstaller
```

### 第二步

运行打包脚本：

```bash
python build_windows_exe.py
```

### 第三步

打包完成后，程序通常会出现在：

```text
dist/PaperReader.exe
```

把这个 `PaperReader.exe` 发给别人后，对方可以直接双击使用。

---

## 5. 导出 PDF 说明

导出 PDF 时：

- macOS 默认使用内置导出器
- Windows 默认尝试调用本机的 Edge、Chrome 或 Chromium

所以在 Windows 上，如果需要导出 PDF，建议系统里安装下面任意一个浏览器：

- Microsoft Edge
- Google Chrome
- Chromium

---

## 6. 常见问题

### 1. 图片在网页里能看到，PDF 里看不到

如果还遇到这个问题：

1. 重新打开阅读器
2. 再导出一次 PDF
3. 确认原文里的图片路径没有丢失

### 2. 目录显示不整齐

程序会尽量把常见论文目录整理成更适合阅读的形式。

如果原始 Markdown 很乱，仍然可能有少量条目不够完美。

### 3. 参考文献挤在一起

程序会自动把 `[1]`、`[2]` 这类参考文献拆成单独条目，并增加间距。

### 4. Windows 上不能导出 PDF

先检查系统里是否安装了：

- Edge
- Chrome
- Chromium

如果一个都没有，先安装一个浏览器再试。

### 5. 双击没反应

可以直接用命令行启动：

```bash
python3 launch_reader.py
```

Windows 下也可以用：

```bash
python launch_reader.py
```

---

## 7. 和启动有关的文件

普通用户一般只需要知道这些：

- `Paper Reader.app`
- `Markdown Reader.command`
- `launch_reader.bat`
- `launch_reader.py`

如果要打包 Windows 程序，还会用到：

- `build_windows_exe.py`
- `paper_reader_windows.pyw`
- `paper_reader_windows.spec`

---

## 8. 一句话总结

如果你使用 macOS：

- 直接打开 `Paper Reader.app`

如果你使用 Windows：

- 开发环境先用 `launch_reader.bat`
- 打包后直接用 `PaperReader.exe`
