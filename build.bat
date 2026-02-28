@echo off
echo ========================================
echo TapNow AI Video Creator - Build Script
echo ========================================
echo.

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building executable...
pyinstaller build.spec --clean

echo.
if exist "dist\TapNow.exe" (
    echo Build successful!
    echo Executable: dist\TapNow.exe
) else (
    echo Build failed!
)

echo.
pause
