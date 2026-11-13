@echo off
title 弓道AI道場
echo ==============================================
echo       弓道AI道場 (Kyudo AI Chat)
echo ==============================================
echo.
echo アプリケーションを起動しています...
echo ブラウザが自動的に開きます。
echo 終了するときは、この画面を閉じるか Ctrl+C を押してください。
echo.
cd /d "%~dp0"
python -m streamlit run app.py --server.headless false
pause
