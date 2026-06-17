@echo off
chcp 65001 >nul
REM 리뷰 수집용 '로그인 크롬'을 9222 포트로 띄웁니다.
REM 이 창에서 쿠팡·네이버(스마트스토어)에 로그인해 두세요. (처음 1회만)
REM 로그인 정보는 아래 browser_profile 폴더에 저장돼 다음부터 자동 유지됩니다.

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
    echo 크롬을 찾을 수 없습니다. chrome.exe 경로를 이 파일에서 직접 지정하세요.
    pause
    exit /b
)

start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%~dp0browser_profile" https://www.coupang.com https://nid.naver.com/nidlogin.login

echo.
echo [열림] 이 크롬 창에서 쿠팡과 네이버에 로그인하세요. (창은 그대로 둔 채로 도구에서 '리뷰 수집')
echo 닫지 마세요. 닫으면 리뷰 수집이 안 됩니다.
