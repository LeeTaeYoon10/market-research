@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 가상환경 확인...
if not exist ".venv\" (
    echo 처음 실행 - 환경을 설치합니다. 몇 분 걸릴 수 있어요.
    py -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m playwright install chromium
) else (
    call .venv\Scripts\activate.bat
)

echo [2/3] (선택) AI 요약을 켜려면 아래 줄의 앞 REM 을 지우고 키를 넣으세요.
REM set ANTHROPIC_API_KEY=sk-ant-여기에-키

echo [3/3] 서버 실행 - 브라우저에서 http://127.0.0.1:5000 열기
start http://127.0.0.1:5000
python app.py

pause
