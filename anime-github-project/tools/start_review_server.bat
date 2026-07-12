@echo off
rem レビュー用ローカルサーバー: リポジトリ直下(project_mana_gh_pages)を8013で配信
rem ※OneDriveミラーは2026-07棚卸しで廃止。必ずこのbatから起動すること
cd /d "%~dp0..\.."
start "" http://localhost:8013/13th-register-kamishibai/review.html
"C:\Users\qvf03\AppData\Local\Python\bin\python.exe" -m http.server 8013 --directory "%CD%"
