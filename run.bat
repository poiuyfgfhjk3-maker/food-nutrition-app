@echo off
chcp 65001 > nul
echo ==========================================================
echo  🥗 식약처 영양성분 DB 기반 AI 푸드 영양 스캐너 실행 중...
echo ==========================================================

cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe run.py
) else (
    py run.py
)

pause
