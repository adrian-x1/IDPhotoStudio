@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "LOG_FILE=%CD%\windows-one-click.log"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "STAGE=initialization"

> "%LOG_FILE%" echo idphoto Windows one-click build log
>> "%LOG_FILE%" echo Started: %DATE% %TIME%
>> "%LOG_FILE%" echo Project: %CD%

set "STAGE=1/8 payload check"
call :stage "[1/8] Checking package files"
if not exist "main.py" goto :missing_payload
if not exist "build.spec" goto :missing_payload
if not exist "requirements.txt" goto :missing_payload
if not exist "requirements-build.txt" goto :missing_payload
if not exist "windows-wheels\" goto :missing_payload
if not exist "windows-wheels\*.whl" goto :missing_payload
for %%F in (isnet-general-use.onnx face_landmarker.task blaze_face_short_range.tflite) do (
    if not exist "assets\models\%%F" goto :missing_payload
)

set "STAGE=2/8 Python check"
call :stage "[2/8] Checking Python 3.13 x64"
python -c "import struct, sys; assert sys.version_info[:2] == (3, 13), sys.version; assert struct.calcsize('P') * 8 == 64, 'Python must be 64-bit'; print(sys.version); print('PYTHON_64BIT_OK')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

set "STAGE=3/8 virtual environment"
call :stage "[3/8] Creating or checking .venv"
if not exist "%VENV_PY%" (
    python -m venv ".venv" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 goto :fail
)
"%VENV_PY%" -c "import struct, sys; assert sys.version_info[:2] == (3, 13), sys.version; assert struct.calcsize('P') * 8 == 64; print('VENV_OK')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

set "STAGE=4/8 offline dependency install"
call :stage "[4/8] Installing dependencies from windows-wheels"
"%VENV_PY%" -m pip install --no-index --find-links="%CD%\windows-wheels" -r requirements.txt -r requirements-build.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

set "STAGE=5/8 dependency validation"
call :stage "[5/8] Checking dependencies and imports"
"%VENV_PY%" -m pip check >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail
"%VENV_PY%" -c "import cv2, mediapipe, onnxruntime, PIL, PySide6, pymatting, rembg; print('IMPORT_OK')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

set "STAGE=6/8 test suite"
call :stage "[6/8] Running tests"
set "QT_QPA_PLATFORM=offscreen"
"%VENV_PY%" -m unittest discover -s tests -v >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    set "QT_QPA_PLATFORM="
    goto :fail
)
set "QT_QPA_PLATFORM="

set "STAGE=7/8 clean build"
call :stage "[7/8] Cleaning build and creating Windows app"
if exist "%CD%\build" rmdir /S /Q "%CD%\build" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail
if exist "%CD%\dist" rmdir /S /Q "%CD%\dist" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail
"%VENV_PY%" -m PyInstaller --clean --noconfirm build.spec >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :fail

set "STAGE=8/8 launch"
call :stage "[8/8] Verifying and starting idphoto.exe"
if not exist "%CD%\dist\idphoto\idphoto.exe" goto :missing_exe
>> "%LOG_FILE%" echo BUILD_OK: %CD%\dist\idphoto\idphoto.exe
start "" "%CD%\dist\idphoto\idphoto.exe"
if errorlevel 1 goto :fail

echo.
echo SUCCESS: idphoto has been built and started.
echo Log: "%LOG_FILE%"
>> "%LOG_FILE%" echo Finished successfully: %DATE% %TIME%
exit /b 0

:missing_payload
>> "%LOG_FILE%" echo ERROR: Required package file is missing.
goto :fail

:missing_exe
>> "%LOG_FILE%" echo ERROR: dist\idphoto\idphoto.exe was not created.
goto :fail

:fail
echo.
echo FAILED at stage %STAGE%.
echo Full log: "%LOG_FILE%"
>> "%LOG_FILE%" echo FAILED at stage %STAGE%: %DATE% %TIME%
pause
exit /b 1

:stage
echo.
echo %~1
>> "%LOG_FILE%" echo.
>> "%LOG_FILE%" echo %~1
exit /b 0
