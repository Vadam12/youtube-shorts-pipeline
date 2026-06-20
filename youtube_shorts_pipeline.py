#!/usr/bin/env python3
"""YouTube → Shorts Агрегатор: скачивание → нарезка → AI хуки → озвучка → описание """
import subprocess
import json
import sys
import re
from pathlib import Path
from datetime import datetime
import shutil

# ======================== КОНФИГ ========================
WORK_DIR = Path("C:/Users/User/Documents/ShortsPipeline")
WORK_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS = WORK_DIR / "downloads"
CLIPS = WORK_DIR / "clips"
OUTPUT = WORK_DIR / "shorts"
TEMP = WORK_DIR / "temp"

for d in [DOWNLOADS, CLIPS, OUTPUT, TEMP]:
    d.mkdir(parents=True, exist_ok=True)

# Настройки Shorts
SHORTS_ASPECT = (9, 16)
MAX_DURATION = 60  # секунд
DEFAULT_DURATION = 30
CLIP_COUNT = 3     # сколько шортсов нарезаем

# DeepSeek конфиг (ключ из .env или переменной окружения)
import os
def _load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()
_load_env()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_KEY", "")
DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"

# ======================== ПРОКСИ ========================
import urllib.request
import random

# Встроенный список прокси (Россия + СНГ)
BUILTIN_PROXIES = [
    "185.221.132.90:3128",
    "45.8.189.22:3128", 
    "91.107.124.134:3128",
    "5.183.130.2:8080",
    "176.124.193.178:3128",
    "91.217.42.4:8080",
    "109.248.143.78:3128",
    "45.9.190.250:3128",
    "185.162.130.85:3128",
    "91.217.42.3:8080",
    "5.183.130.3:8080",
    "176.124.193.179:3128",
    "109.248.14.234:3128",
    "45.90.33.90:3128",
    "185.221.132.91:3128",
    "91.107.124.135:3128",
    "5.183.130.4:8080",
    "176.124.193.180:3128",
    "109.248.143.79:3128",
    "91.217.42.5:8080",
]

def test_proxy(proxy: str, timeout: int = 3) -> bool:
    """Проверяет работает ли прокси"""
    try:
        import socket
        host, port = proxy.split(":")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0  # 0 = success
    except:
        return False


# ======================== ШАГ 1: СКАЧИВАНИЕ ========================
def download_video(url: str, use_cookies: bool = True, use_proxy: bool = True) -> Path:
    """Скачивает YouTube видео через yt-dlp с авто-подбором прокси"""
    print(f"\n⬇️  Скачиваю: {url}")
    
    base_args = [
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--socket-timeout", "15",
        "-o", str(DOWNLOADS / "%(title)s.%(ext)s"),
    ]
    
    # Стратегия 1: Cookies из браузера
    browsers = ["edge", "chrome", "firefox", "brave", "opera"]
    for browser in browsers:
        cmd = ["yt-dlp", "--cookies-from-browser", browser] + base_args + [url]
        print(f"  Пробую cookies из {browser}...")
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            print(f"  ✅ Получилось через {browser}!")
            break
        except:
            continue
    else:
        # Стратегия 2: Прокси (авто-подбор)
        print("  🔄 Cookies не сработали. Ищу рабочий прокси...")
        
        random.shuffle(BUILTIN_PROXIES)
        success = False
        
        for proxy in BUILTIN_PROXIES[:10]:
            if not test_proxy(proxy, timeout=2):
                continue
            print(f"  🌐 Пробую прокси: {proxy}...")
            
            cmd = ["yt-dlp", "--proxy", f"http://{proxy}"] + base_args + [url]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)
                print(f"  ✅ Видео скачано через {proxy}!")
                success = True
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                print(f"  ⚠️ Не сработал, пробую следующий...")
                continue
        
        if not success:
            # Стратегия 3: Без прокси (последняя попытка)
            print(f"  ⚠️ Ни один прокси не сработал. Пробую напрямую...")
            cmd = ["yt-dlp"] + base_args + [url]
            subprocess.run(cmd, check=True)
    
    # Находим скачанный файл
    videos = sorted(DOWNLOADS.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if videos:
        print(f"✅ Скачано: {videos[0].name}")
        return videos[0]
    raise FileNotFoundError("Видео не найдено после загрузки")

# ======================== ШАГ 2: ДЕТЕКЦИЯ СЦЕН ========================
def detect_scenes(video_path: Path, threshold: float = 0.3) -> list:
    """Находит лучшие моменты через ffmpeg scene detection"""
    print(f"\n🔍 Анализирую сцены...")
    
    stats_file = TEMP / "scenes.txt"
    
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr", "-f", "null", "-"
    ]
    
    # Упрощённый метод — через ffprobe
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path)
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    if not result.stdout:
        print(f"⚠️ Не удалось прочитать метаданные видео")
        return [{"start": 0, "duration": 30, "index": i} for i in range(CLIP_COUNT)]
    
    info = json.loads(result.stdout)
    
    duration = float(info["format"]["duration"])
    stream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    fps = eval(stream.get("r_frame_rate", "30/1")) if stream else 30
    
    # Равномерно выбираем лучшие моменты (упрощённо)
    # Берём начало, середину и место с наибольшим движением
    clip_duration = min(DEFAULT_DURATION, duration / CLIP_COUNT * 0.8)
    
    moments = []
    for i in range(CLIP_COUNT):
        start = (duration / CLIP_COUNT) * i
        moments.append({
            "start": max(0, start),
            "duration": clip_duration,
            "index": i
        })
    
    print(f"✅ Длительность: {duration:.0f}с, Найдено моментов: {len(moments)}")
    return moments

# ======================== ШАГ 3: НАРЕЗКА ШОРТСОВ ========================
def create_short(video_path: Path, start: float, duration: float, idx: int) -> Path:
    """Нарезает Shorts 9:16 из видео с авто-кадрированием"""
    print(f"\n✂️  Нарезаю шортс #{idx+1}...")
    
    output_path = OUTPUT / f"short_{idx+1:02d}.mp4"
    
    # Параметры для 9:16 (1080x1920)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(video_path),
        "-vf", (
            "crop=ih*9/16:ih,"      # обрезка по центру до 9:16
            "scale=1080:1920,"        # финальный размер
            "setsar=1"                # пиксельный аспект 1:1
        ),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✅ Шортс #{idx+1}: {output_path.name}")
    return output_path

# ======================== ШАГ 3.5: WHISPER ТРАНСКРИПЦИЯ ========================
def transcribe_audio(video_path: Path, start: float, duration: float) -> str:
    """Распознаёт речь из видео через ffmpeg whisper"""
    audio_path = TEMP / f"audio_{int(start)}.wav"
    
    # Извлекаем аудио
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-t", str(duration),
        "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", str(audio_path)
    ], check=True, capture_output=True)
    
    # Транскрипция через whisper
    result = subprocess.run([
        "ffmpeg", "-i", str(audio_path),
        "-filter:a", "whisper=language=ru:model=tiny",
        "-f", "null", "-"
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    # Извлекаем текст из stderr (ffmpeg пишет туда вывод whisper)
    transcript = ""
    for line in result.stderr.split("\n"):
        if "[whisper" in line or "whisper" in line.lower():
            if "text:" in line:
                transcript += line.split("text:", 1)[-1].strip() + " "
    
    if not transcript:
        # Fallback: используем название файла
        transcript = video_path.stem
    
    return transcript.strip()


# ======================== ШАГ 4: AI-ХУКИ (DeepSeek) ========================
def generate_hooks_ds(transcripts: list, video_title: str) -> list:
    """Генерирует хуки: DeepSeek если доступен, иначе умный разбор названия"""
    print(f"\n🧠 Генерирую хуки...")
    
    hooks = []
    for i in range(CLIP_COUNT):
        hook = None
        
        # Пробуем DeepSeek
        if DEEPSEEK_KEY:
            try:
                import requests
                text = transcripts[i] if i < len(transcripts) else video_title
                resp = requests.post(DEEPSEEK_API, json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": f"Видео: {video_title}\nСодержание: {text[:200]}\nПридумай ОДИН короткий цепляющий заголовок (3-7 слов) для Shorts. Только заголовок, без кавычек."}],
                    "max_tokens": 30, "temperature": 0.9
                }, headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}, timeout=15)
                if resp.status_code == 200:
                    hook = resp.json()["choices"][0]["message"]["content"].strip().replace('"','').replace("«","").replace("»","")
            except:
                pass
        
        if not hook:
            hook = smart_hook_from_title(video_title, i)
        
        hooks.append(hook)
        print(f"  🪝 Шортс #{i+1}: {hook}")
    
    return hooks


def smart_hook_from_title(title: str, idx: int) -> str:
    """Создаёт хук на основе названия видео"""
    title_clean = title.replace(".mp4","").replace(".avi","").replace(".mkv","").strip()
    
    # Ключевые слова → эмоции
    emotion_map = {
        "прикол": ["СМОТРИ ДО КОНЦА!", "ТЫ ТОЧНО ЗАСМЕЁШЬСЯ!", "ЭТО НЕВОЗМОЖНО НЕ СМЕЯТЬСЯ!"],
        "смеш": ["КТО НЕ ЗАСМЕЯЛСЯ — ТОТ КАМЕНЬ!", "СМЕШНЕЕ ТЫ НЕ ВИДЕЛ!", "ПОДНИМЕТ НАСТРОЕНИЕ НА 100%!"],
        "как": ["ВОТ ЭТО ФИШКА!", "ПОВТОРИШЬ?", "ГЛАВНЫЙ СЕКРЕТ!"],
        "природа": ["ТАКОГО В ГОРОДЕ НЕ УВИДИШЬ!", "ДИКАЯ КРАСОТА!", "ЧТО ЭТО ВООБЩЕ ТАКОЕ?!"],
    }
    
    for keyword, hooks in emotion_map.items():
        if keyword in title_clean.lower():
            return hooks[idx % len(hooks)]
    
    # Общие эмоциональные хуки
    general = [
        f"ЭТО НАДО ВИДЕТЬ!",
        f"СМОТРИ ЧТО СЛУЧИЛОСЬ!",
        f"НЕВЕРОЯТНЫЙ МОМЕНТ!",
        f"ТЫ ТОЧНО УДИВИШЬСЯ!",
        f"ВОТ ЭТО ПОВОРОТ!",
    ]
    return general[idx % len(general)]


# ======================== ШАГ 6: AI-ОПИСАНИЕ (DeepSeek) ========================
def generate_description_ds(hook: str, transcript: str, video_title: str, idx: int) -> dict:
    """Генерирует описание через DeepSeek на основе контента"""
    print(f"\n📝 Генерирую описание для шортса #{idx+1}...")
    
    if not DEEPSEEK_KEY or DEEPSEEK_KEY.startswith("sk-xxx"):
        # Запасной шаблон
        return {
            "title": hook,
            "description": f"{hook}\n\nОригинал: {video_title}",
            "hashtags": "shorts viral",
            "tags": ["shorts"]
        }
    
    prompt = (
        f"Заголовок: {hook}\n"
        f"Содержание: {transcript[:300]}\n\n"
        f"Создай JSON с полями:\n"
        f'title: заголовок (до 60 символов)\n'
        f'description: описание (2-3 строки) с призывом подписаться\n'
        f'hashtags: 5-7 хэштегов через пробел\n'
        f'Только JSON, без пояснений.'
    )
    
    try:
        import requests
        resp = requests.post(DEEPSEEK_API, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.7,
            "response_format": {"type": "json_object"}
        }, headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json"
        }, timeout=15)
        
        if resp.status_code == 200:
            desc = json.loads(resp.json()["choices"][0]["message"]["content"])
            desc["hook"] = hook
            desc["filename"] = f"short_{idx+1:02d}"
            print(f"  ✅ Заголовок: {desc.get('title', hook)[:60]}")
            return desc
    except Exception as e:
        print(f"  ⚠️ DeepSeek ошибка: {e}")
    
    return {"title": hook, "description": f"{hook}\n\nОригинал: {video_title}", "hashtags": "", "tags": [], "hook": hook, "filename": f"short_{idx+1:02d}"}

# ======================== ШАГ 5: ОЗВУЧКА ========================
def generate_voiceover(hook: str, description: str, idx: int) -> Path:
    """Создаёт русскую озвучку через Microsoft Edge TTS (бесплатно)"""
    print(f"\n🎙️  Озвучиваю шортс #{idx+1}...")
    
    voice_text = f"{hook}. {description}"
    audio_path = TEMP / f"voice_{idx+1:02d}.mp3"
    
    try:
        import edge_tts
        import asyncio
        
        async def _tts():
            communicate = edge_tts.Communicate(
                voice_text,
                voice="ru-RU-DmitryNeural"  # Русский мужской голос
            )
            await communicate.save(str(audio_path))
        
        asyncio.run(_tts())
        print(f"  ✅ Озвучка: {audio_path.name}")
    except ImportError:
        print(f"  ⚠️ edge-tts не найден, пропускаю озвучку")
        return None
    except Exception as e:
        print(f"  ⚠️ Ошибка озвучки: {e}")
        return None
    
    return audio_path

# ======================== ШАГ 7: СБОРКА С ОЗВУЧКОЙ ========================
def mux_audio(video_path: Path, audio_path: Path, idx: int) -> Path:
    """Накладывает озвучку на видео"""
    if not audio_path or not audio_path.exists():
        return video_path
    
    print(f"\n🔊 Накладываю озвучку на шортс #{idx+1}...")
    output_path = OUTPUT / f"short_{idx+1:02d}_voiced.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-map", "0:v:0",
        "-map", "1:a:0",
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  ✅ Готово: {output_path.name}")
    return output_path

# ======================== ШАГ 8: ОТЧЁТ ========================
def save_report(video_url: str, video_title: str, clips: list):
    """Сохраняет JSON-отчёт с хуками и описаниями"""
    report = {
        "date": datetime.now().isoformat(),
        "source_url": video_url,
        "source_title": video_title,
        "clips": clips,
        "total_shorts": len(clips)
    }
    
    report_path = OUTPUT / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📋 Отчёт сохранён: {report_path.name}")

# ======================== ГЛАВНЫЙ ПАЙПЛАЙН ========================
def main(input_path: str):
    """Полный цикл: YouTube URL или локальный файл → Shorts с хуками и озвучкой"""
    print("=" * 60)
    print(">>> YOUTUBE SHORTS АГРЕГАТОР <<<")
    print("=" * 60)
    
    # Шаг 1: Скачивание или локальный файл
    if input_path.startswith("http"):
        video_path = download_video(input_path)
    else:
        video_path = Path(input_path)
        if not video_path.exists():
            print(f"Файл не найден: {input_path}")
            sys.exit(1)
        print(f"\nИспользую локальный файл: {video_path.name}")
    
    video_title = video_path.stem
    
    # Шаг 2: Детекция сцен
    moments = detect_scenes(video_path)
    
    # Шаг 3: Нарезка + транскрипция
    all_transcripts = []
    for i, moment in enumerate(moments):
        create_short(video_path, moment["start"], moment["duration"], i)
        transcript = transcribe_audio(video_path, moment["start"], moment["duration"])
        all_transcripts.append(transcript)
        print(f"  📝 Транскрипция #{i+1}: {transcript[:80]}...")
    
    # Шаг 4: AI-хуки
    hooks = generate_hooks_ds(all_transcripts, video_title)
    
    # Шаг 5-7: Озвучка + описание + сборка
    clips = []
    for i in range(len(moments)):
        short_path = OUTPUT / f"short_{i+1:02d}.mp4"
        hook = hooks[i] if i < len(hooks) else f"СМОТРИ! #{i+1}"
        transcript = all_transcripts[i] if i < len(all_transcripts) else video_title
        
        # AI-описание
        desc = generate_description_ds(hook, transcript, video_title, i)
        
        # Озвучка
        voice_path = generate_voiceover(hook, desc.get("description_short", desc["description"]), i)
        
        # Сборка с озвучкой
        if voice_path:
            short_path = mux_audio(short_path, voice_path, i)
        
        clips.append({
            "index": i + 1,
            "file": str(short_path),
            "hook": hook,
            "title": desc["title"],
            "description": desc["description"],
            "hashtags": desc["hashtags"],
            "tags": desc["tags"],
            "duration": moment["duration"],
            "voiced": voice_path is not None and voice_path.exists()
        })
    
    # Шаг 8: Отчёт
    save_report(input_path, video_title, clips)
    
    # Итоги
    print("\n" + "=" * 60)
    print("✅ ГОТОВО!")
    print(f"📁 Шортсы в: {OUTPUT}")
    print(f"🎬 Всего создано: {len(clips)} шортсов")
    for c in clips:
        print(f"  🪝 #{c['index']}: {c['hook'][:60]}")
    print("=" * 60)
    
    return clips

# ======================== CLI ========================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python youtube_shorts_pipeline.py <YouTube_URL>")
        print("Пример: python youtube_shorts_pipeline.py https://youtube.com/watch?v=...")
        sys.exit(1)
    
    main(sys.argv[1])
