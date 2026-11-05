@echo off
rem ============================================================
rem  双击运行：抓取资讯并更新 index.html
rem  注意：本文件保存为 ANSI(GBK) 编码，用记事本修改后请另存为 ANSI
rem ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

rem 记录当前控制台代码页，跑完 Python 再切回来，避免中文乱码
for /f "tokens=2 delims=:" %%a in ('chcp') do set "OLDCP=%%a"
set "OLDCP=%OLDCP: =%"
if not defined OLDCP set "OLDCP=936"

rem 依次尝试：本机 Anaconda -> PATH 里的 python
set "PY="
if exist "D:\soft\Anaconda3\python.exe" set "PY=D:\soft\Anaconda3\python.exe"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :nopython

echo.
echo ============================================================
echo   多领域行业资讯 · 每日抓取
echo   人工智能 / 嵌入式 / 汽车 / 机器人 / 医疗 / 前沿
echo ============================================================
echo   正在抓取，约需 1-2 分钟，请稍候...
echo.

chcp 65001 >nul
"%PY%" "%~dp0Demo\fetch_industry_news.py" %*
set "RC=%ERRORLEVEL%"
chcp %OLDCP% >nul

echo.
if "%RC%"=="0" (
  echo [完成] 已更新今天的 CSV / TXT / MD 和 index.html
  echo        双击 index.html 即可查看最新资讯
) else (
  echo [失败] 退出码 %RC%，详情见 worknews\logs\ 下当天日志
)
echo.
echo 按任意键关闭窗口...
pause >nul
endlocal & exit /b %RC%

:nopython
echo.
echo [错误] 没有找到 Python。
echo        请先安装 Python 3.8+（安装时勾选 "Add Python to PATH"），
echo        或者用记事本打开本文件，把 Anaconda 那一行改成你自己的 python.exe 路径。
echo.
echo 按任意键关闭窗口...
pause >nul
endlocal & exit /b 1
