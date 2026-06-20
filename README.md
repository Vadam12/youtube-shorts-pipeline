# 🎬 YouTube Shorts Pipeline

Автоматический конвейер: YouTube видео → нарезка Shorts 9:16 → AI-хуки → озвучка → описание.

## Возможности

- 📥 Скачивание видео с YouTube (yt-dlp + прокси + cookies)
- ✂️ Детекция сцен и нарезка в вертикальный формат 9:16 (ffmpeg)
- 🧠 AI-хуки на основе содержания (DeepSeek API + локальный генератор)
- 🎙️ Русская озвучка (Microsoft Edge TTS)
- 📝 AI-описания, теги, хэштеги (DeepSeek)
- 🎵 Транскрипция аудио (Whisper через ffmpeg)
- 📁 Поддержка локальных файлов

## Быстрый старт

```bash
# Из YouTube
python youtube_shorts_pipeline.py "https://youtube.com/watch?v=..."

# Из локального файла
python youtube_shorts_pipeline.py "C:/video.mp4"
```

Или просто запусти `ЗАПУСК.bat` и вставь ссылку.

## Стек

- Python 3.11+
- ffmpeg (с whisper)
- yt-dlp
- edge-tts
- DeepSeek API

## Структура

```
ShortsPipeline/
├── youtube_shorts_pipeline.py  # Основной скрипт
├── ЗАПУСК.bat                  # Быстрый запуск
├── downloads/                  # Скачанные видео
├── clips/                      # Промежуточные нарезки
├── shorts/                     # Готовые Shorts
├── temp/                       # Временные файлы
└── README.md
```

## Автор

**Вадим** — ML Engineer, AI Automation Specialist
- GitHub: [github.com/Vadam12](https://github.com/Vadam12)
- Курс по n8n: [tonygoy.ru](https://tonygoy.ru)
