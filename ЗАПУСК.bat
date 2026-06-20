@echo off
chcp 65001 >nul
echo 🎬 YouTube Shorts Агрегатор
echo.
set /p URL="Введи ссылку на YouTube видео: "
echo.
python "C:\Users\User\Documents\ShortsPipeline\youtube_shorts_pipeline.py" %URL%
echo.
pause
