@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo Project MANA setup
echo ========================================

set "PYTHON_EXE="
set "SYSTEM_PYTHON="

echo [1/4] Python check...
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo Existing .venv found.
) else (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "SYSTEM_PYTHON=py -3"
    ) else (
        python --version >nul 2>&1
        if not errorlevel 1 (
            set "SYSTEM_PYTHON=python"
        )
    )
)

if not defined PYTHON_EXE (
    if not defined SYSTEM_PYTHON (
        echo Python was not found.
        echo Install Python 3.12 or later and enable "Add python.exe to PATH".
        echo Then run setup_app.bat again.
        pause
        exit /b 1
    )
)

echo [2/4] Create virtual environment...
if not exist ".venv\Scripts\python.exe" (
    %SYSTEM_PYTHON% -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv.
        pause
        exit /b 1
    )
)
set "PYTHON_EXE=.venv\Scripts\python.exe"

echo [3/4] Install requirements...
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip was not found in .venv. Trying ensurepip...
    "%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>&1
    if errorlevel 1 (
        echo ensurepip failed. Checking whether required packages already exist...
        "%PYTHON_EXE%" -c "import streamlit, openai, dotenv" >nul 2>&1
        if errorlevel 1 (
            echo Failed to install pip with ensurepip.
            echo Recreate .venv after installing Python with pip support.
            pause
            exit /b 1
        ) else (
            echo Required packages are already available. Skipping pip install.
            goto INIT_DB
        )
    )
)

"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

:INIT_DB
echo [4/4] Initialize database...
"%PYTHON_EXE%" src\import_cards.py
if errorlevel 1 (
    echo Failed to initialize database.
    pause
    exit /b 1
)

echo.
echo Setup complete.
echo Run run_app.bat next.
pause
