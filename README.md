# Paper Reader 使用说明

Paper Reader 是一个用来阅读论文 Markdown 的小工具。

它适合看这类文件：

- `.md`
- `.markdown`
- `.txt`

它支持这些常用功能：

- 打开本地论文文件
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

1. 选择你的论文 `.md` 文件
2. 浏览器会自动打开阅读器页面
3. 需要导出 PDF 时，点击页面里的 `导出 PDF`

### Windows

如果你已经有打包好的程序，直接双击：

- `PaperReader.exe`

如果你现在还没有 `.exe`，可以先双击：

- `launch_reader.bat`

打开后：

1. 选择你的论文 `.md` 文件
2. 浏览器会自动打开阅读器页面
3. 需要导出 PDF 时，点击页面里的 `导出 PDF`

---

## 2. 如果你是第一次使用

你至少需要有：

- Python 3.9 或更高版本
- 一个你要阅读的 Markdown 文件

如果你不确定自己有没有 Python：

- macOS 打开终端输入 `python3 --version`
- Windows 打开命令提示符输入 `python --version`

只要能看到版本号，就说明可以继续。

---

## 3. 手动启动方法

如果双击打不开，可以手动运行。

### macOS / Windows 通用方法

在项目目录运行：

```bash
python3 md_reader/launch_reader.py
```

如果你想直接指定文件：

```bash
python3 md_reader/launch_reader.py "/absolute/path/to/your-file.md"
```

Windows 里也可以写成：

```bash
python md_reader/launch_reader.py "C:\\path\\to\\your-file.md"
```

打开后，浏览器地址一般是：

```text
http://read-md.localhost:8765
```

---

## 4. Windows 怎么生成 exe

如果你想把它做成 Windows 程序：

### 第一步

安装 PyInstaller：

```bash
pip install pyinstaller
```

### 第二步

运行打包脚本：

```bash
python md_reader/build_windows_exe.py
```

### 第三步

打包完成后，程序通常会出现在：

```text
dist/PaperReader.exe
```

以后把这个 `PaperReader.exe` 给别人，别人就可以直接双击使用。

---

## 5. 导出 PDF 说明

导出 PDF 时：

- macOS 默认使用内置导出器
- Windows 默认尝试调用本机的 Edge / Chrome / Chromium

所以在 Windows 上，如果你要导出 PDF，电脑里最好安装下面任意一个浏览器：

- Microsoft Edge
- Google Chrome
- Chromium

---

## 6. 常见问题

### 1. 图片在网页里能看到，PDF 里看不到

现在程序已经对导出做了修复。

如果还遇到这个问题：

1. 重新打开阅读器
2. 再导出一次 PDF
3. 确认原文里的图片路径本身没有丢失

### 2. 目录显示不整齐

程序会自动把常见论文目录尽量整理成标准点线目录。

但如果原始 Markdown 非常乱，仍然可能有少量条目不完美。

### 3. 参考文献挤在一起

程序会自动把 `[1]`、`[2]` 这种参考文献拆成单独条目，并增加间距。

### 4. Windows 上不能导出 PDF

先检查电脑里有没有：

- Edge
- Chrome
- Chromium

如果一个都没有，先装一个浏览器再试。

### 5. 双击没反应

可以直接用命令行启动：

```bash
python3 md_reader/launch_reader.py
```

或者 Windows 下：

```bash
python md_reader/launch_reader.py
```

---

## 7. 这个项目里和启动有关的文件

普通用户一般只需要知道这些：

- `Paper Reader.app`
- `Markdown Reader.command`
- `launch_reader.bat`
- `launch_reader.py`

如果你要打包 Windows 程序，还会用到：

- `build_windows_exe.py`
- `paper_reader_windows.pyw`
- `paper_reader_windows.spec`

---

## 8. 一句话总结

如果你是 mac 用户：

- 直接打开 `Paper Reader.app`

如果你是 Windows 用户：

- 先用 `launch_reader.bat`
- 以后可以打包成 `PaperReader.exe`



<img width="966" height="337" alt="image" src="https://github.com/user-attachments/assets/957a2121-e355-4ccd-9f38-3163934534a9" />
