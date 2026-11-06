@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JobBot

if not exist ".env" copy ".env.exemple" ".env" >nul
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do if not "%%b"=="" set "%%a=%%b"

if "%ANTHROPIC_API_KEY%"=="" (
  echo.
  echo  Il manque ta cle API Anthropic.
  echo  Colle-la apres ANTHROPIC_API_KEY= dans le fichier qui s ouvre, enregistre, puis relance ce fichier.
  echo.
  start "" notepad ".env"
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo  Premiere installation, patiente une minute...
  py -m venv venv
  if errorlevel 1 goto :nopython
  venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :pipfail
)

set HOST=127.0.0.1
set PORT=5000
echo.
echo  JobBot tourne sur http://localhost:5000
echo  Ferme cette fenetre pour l arreter.
echo.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:5000"
venv\Scripts\python.exe app.py
pause
exit /b 0

:nopython
echo  Python est introuvable. Installe-le depuis https://www.python.org/downloads/ puis relance.
pause
exit /b 1

:pipfail
echo  L installation des dependances a echoue. Verifie ta connexion internet puis relance.
rmdir /s /q venv
pause
exit /b 1
