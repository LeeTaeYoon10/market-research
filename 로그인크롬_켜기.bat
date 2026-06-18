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
echo [안내] 이건 보통 실행할 필요 없습니다. 도구에서 '네이버 리뷰 자동 수집'을 누르면
echo        프로그램이 화면 밖에 크롬을 알아서 띄워 수집합니다(작업 방해 없음).
echo        쿠팡 리뷰를 직접 로그인해서 보고 싶을 때만 이 파일을 쓰세요.
echo.

REM 전용 프로필 + 화면 밖(-2400) 위치로 별도 크롬 기동(detached). powershell로 띄워 cmd창 즉시 닫힘.
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process '%CHROME%' -ArgumentList '--remote-debugging-port=9222','--user-data-dir=\"%~dp0browser_profile\"','--window-position=-2400,-2400','--window-size=1400,1000','about:blank'"
echo 백그라운드 크롬(화면 밖)을 켰습니다. 이 창은 닫아도 됩니다.
