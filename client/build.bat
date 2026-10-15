@echo off
setlocal
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo Install Visual Studio with the C++ tools, then run this again.
  exit /b 1
)
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS=%%i"
if not defined VS (
  echo Visual Studio C++ tools were not found.
  exit /b 1
)
call "%VS%\VC\Auxiliary\Build\vcvarsall.bat" x86
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /MT /O2 /W3 /DUNICODE /D_UNICODE /D_CRT_SECURE_NO_WARNINGS lira_hook.cpp /LD /link /OUT:lira_hook.dll user32.lib
if errorlevel 1 exit /b 1
cl /nologo /MT /O2 /W3 /DUNICODE /D_UNICODE /D_CRT_SECURE_NO_WARNINGS lira_launch.cpp /Fe:lira_launch.exe /link /SUBSYSTEM:CONSOLE /ENTRY:wmainCRTStartup user32.lib advapi32.lib
exit /b %errorlevel%
