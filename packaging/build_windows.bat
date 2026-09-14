@echo off
REM Build NFLBlitzModSuite.exe on Windows.
REM
REM Run this from the repository root:  packaging\build_windows.bat
REM Requires Python 3.10+ on PATH. The .exe lands in dist\.

setlocal
cd /d "%~dp0.."

echo === Installing build dependencies ===
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt || goto :error
python -m pip install pyinstaller || goto :error

echo === Running the test suite ===
python -m pytest -q || goto :error

echo === Building ===
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
python -m PyInstaller packaging\nfl_blitz_suite.spec --noconfirm || goto :error

echo.
echo === Done ===
echo Built: dist\NFLBlitzModSuite.exe
goto :eof

:error
echo.
echo Build failed with error %errorlevel%.
exit /b %errorlevel%
