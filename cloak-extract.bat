@echo off
REM cloak-extract launcher: ensures deps are installed, then runs the tool.
setlocal
set "TOOL_DIR=%~dp0"
set "STAMP=%TOOL_DIR%.deps_installed"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

if not exist "%STAMP%" (
    echo [cloak-extract] First run: installing Python dependencies...
    %PY% -m pip install --quiet --disable-pip-version-check -r "%TOOL_DIR%requirements.txt"
    if errorlevel 1 (
        echo [cloak-extract] Dependency install failed. Run: %PY% -m pip install -r "%TOOL_DIR%requirements.txt"
        exit /b 1
    )
    type nul > "%STAMP%"
)

%PY% "%TOOL_DIR%cloak_extract.py" %*
exit /b %ERRORLEVEL%
