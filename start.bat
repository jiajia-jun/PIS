@echo off
chcp 65001 >nul
title PIS-web 全景图像拼接系统

echo ============================================
echo   PIS-web 全景图像拼接系统
echo ============================================
echo.

REM 检查 DATABASE_PIS 环境变量
if not "%DATABASE_PIS%"=="" goto :run

echo [提示] 未检测到 DATABASE_PIS 环境变量
echo.
echo 请设置 MySQL 连接串，格式：
echo   root:密码@tcp(地址:3306)/数据库名?charset=utf8mb4^&parseTime=True
echo.
set /p DB_INPUT="请输入 MySQL 连接串（回车跳过则使用默认值）: "

if "%DB_INPUT%"=="" (
    echo 使用默认连接串...
    set DATABASE_PIS=root:123456@tcp(127.0.0.1:3306)/pis?charset=utf8mb4&parseTime=True
) else (
    set DATABASE_PIS=%DB_INPUT%
)

:run
echo.
echo 正在启动服务...
echo.

REM 检查可执行文件
if not exist "pis-web.exe" (
    echo [错误] 未找到 pis-web.exe，请确认文件存在
    pause
    exit /b 1
)

pis-web.exe

REM 如果 pis-web 异常退出，暂停查看日志
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [错误] 服务异常退出，错误码: %ERRORLEVEL%
    echo 请检查 logs\task.log 查看详细日志
)

pause
