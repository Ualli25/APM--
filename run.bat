@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Установка Flask (нужно только при первом запуске)...
python -m pip install -r requirements.txt
echo.
echo Запуск приложения. Браузер откроется автоматически.
echo Чтобы остановить приложение, закройте это окно или нажмите Ctrl+C.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python app.py
pause
