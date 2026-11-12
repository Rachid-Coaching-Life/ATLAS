@echo off
chcp 65001 > nul
cd /d "%~dp0"
set "SETUP=%~dp0scripts\atlas_voice_setup.py"
if not exist "%SETUP%" set "SETUP=%~dp0atlas_voice_setup.py"
if not exist "%SETUP%" (
  echo Preparation interrompue : programme Python absent.
  pause
  exit /b 1
)
where py > nul 2>&1
if not errorlevel 1 (
  py -3 "%SETUP%"
) else (
  python "%SETUP%"
)
echo.
echo Appuyez sur une touche pour fermer cette fenetre.
pause > nul
