@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo Project MANA start
echo ========================================

if not exist ".venv\Scripts\python.exe" (
    echo .venv was not found.
    echo Run setup_app.bat first.
    pause
    exit /b 1
)

if not exist "data\cards.db" (
    echo data\cards.db was not found. Initializing database...
    ".venv\Scripts\python.exe" src\import_cards.py
    if errorlevel 1 (
        echo Failed to initialize database.
        pause
        exit /b 1
    )
)

echo Starting Streamlit...
echo Open http://localhost:8501 in your browser.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
