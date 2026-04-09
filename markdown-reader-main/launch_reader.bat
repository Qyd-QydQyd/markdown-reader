@echo off
setlocal
set SCRIPT_DIR=%~dp0
if defined PYTHON_BIN (
  set PYTHON_EXE=%PYTHON_BIN%
) else (
  set PYTHON_EXE=python
)
"%PYTHON_EXE%" "%SCRIPT_DIR%launch_reader.py" %*
