@echo off
chcp 65001 > nul
cd /d "%~dp0"
where py > nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0scripts\atlas_voice_setup.py"
) else (
  python "%~dp0scripts\atlas_voice_setup.py"
)
echo.
echo Appuyez sur une touche pour fermer cette fenetre.
pause > nul
