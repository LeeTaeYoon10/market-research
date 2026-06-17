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

echo.
echo [안내] 이 검은 창과 곧 뜨는 크롬 창을 모두 그대로 두세요. (닫으면 리뷰 수집 불가)
echo 크롬 창에서 쿠팡과 네이버에 로그인한 뒤, 도구에서 '리뷰 수집'을 누르세요.
echo.

REM start 로 띄우면 기존 크롬에 흡수돼 디버그포트가 안 열린다.
REM 전용 프로필 + 직접 실행(이 창 유지)으로 별도 인스턴스를 강제한다.
"%CHROME%" --remote-debugging-port=9222 --user-data-dir="%~dp0browser_profile" https://www.coupang.com https://nid.naver.com/nidlogin.login
