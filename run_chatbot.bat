@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo =============================================
echo           Chatbot 시작
echo =============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo  https://www.python.org 에서 Python을 설치해 주세요.
    pause
    exit /b 1
)

echo [1/3] 기존 8501 포트 앱 종료 중...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| find ":8501" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/3] 패키지 설치 중...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [오류] 패키지 설치에 실패했습니다.
    pause
    exit /b 1
)

echo [3/3] Chatbot 실행 중...
echo  브라우저가 자동으로 열립니다. (http://localhost:8501)
echo  종료하려면 이 창을 닫거나 Ctrl+C 를 누르세요.
echo.
python -m streamlit run streamlit_app.py

pause
