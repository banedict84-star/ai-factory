@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title AI Employee OS

echo ============================================
echo    AI Employee OS  시작합니다
echo ============================================
echo.

REM 1) 파이썬 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
  echo [!] 파이썬이 설치되어 있지 않습니다.
  echo.
  echo     1) https://www.python.org/downloads/  접속
  echo     2) 노란 "Download Python" 버튼으로 설치
  echo     3) 설치 첫 화면에서 "Add python.exe to PATH" 를 꼭 체크!
  echo     4) 설치가 끝나면 이 파일을 다시 더블클릭하세요.
  echo.
  pause
  exit /b
)

REM 2) 필요한 프로그램 설치 (처음 한 번은 몇 분 걸립니다)
echo [*] 필요한 프로그램을 준비 중입니다... (처음엔 시간이 좀 걸려요)
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM 3) OpenAI 키 준비 (처음 한 번만 입력하면 openai_key.txt 에 저장됩니다)
if not exist openai_key.txt (
  echo.
  echo [*] OpenAI 키를 붙여넣고 Enter 를 누르세요.
  echo     ^(마우스 오른쪽 클릭 = 붙여넣기^)
  set /p KEY=키 입력:
  >openai_key.txt echo !KEY!
)
set /p OPENAI_API_KEY=<openai_key.txt
set EXECUTOR=openai

REM 4) 4초 뒤 브라우저 자동 열기 + 서버 실행
echo.
echo [*] 곧 브라우저가 열립니다. 안 열리면 주소창에 http://127.0.0.1:8000 를 입력하세요.
echo     (끄려면 이 검은 창을 닫으면 됩니다.)
echo.
start "" /min cmd /c "ping -n 5 127.0.0.1 >nul & start http://127.0.0.1:8000"
python -m oms.main serve

pause
