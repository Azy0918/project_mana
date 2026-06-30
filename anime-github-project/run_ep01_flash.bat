@echo off
chcp 65001 >nul
cd /d "C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages\anime-github-project"
set PYTHONIOENCODING=utf-8
"C:\Users\qvf03\AppData\Local\Python\pythoncore-3.14-64\python.exe" tools\gen_episode_audio.py --script ..\13th-register-kamishibai\scripts\ep01_revised.md --out ..\13th-register-kamishibai\audio\ep01 --model gemini-2.5-flash-preview-tts --throttle 8 > tools\ep01_flash_run.log 2>&1
