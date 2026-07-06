@echo off
rem 第十三レジ エピソードスタジオ起動 (http://localhost:8040 / Tailscale経由でスマホから)
cd /d "%~dp0"
title episode-studio
python episode_studio_server.py
pause
