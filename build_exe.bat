@echo off
rem Builds Pond.exe on Windows. Result: dist\Pond\Pond.exe (zip the whole dist\Pond folder to share it).
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt || goto :error
python -m PyInstaller --noconfirm --clean pond.spec || goto :error
echo.
echo Done: dist\Pond\Pond.exe
goto :eof
:error
echo Build failed.
exit /b 1
