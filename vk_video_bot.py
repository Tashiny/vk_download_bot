import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import yt_dlp
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # https://your-app.onrender.com
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8000))

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Создаем папку для временных файлов
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_vk_video(url: str) -> tuple[str, str]:
    """
    Загружает видео из VK в максимальном качестве
    Возвращает путь к файлу и название
    """
    ydl_opts = {
        'format': 'best',  # Лучшее качество (включая 4K если доступно)
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': False,
        'no_warnings': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            title = info.get('title', 'Видео')
            return filename, title
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        raise


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Привет! Я бот для загрузки видео из VK.\n\n"
        "📹 Просто отправь мне ссылку на видео из VK, и я скачаю его для тебя в максимальном качестве (включая 4K)!\n\n"
        "Примеры ссылок:\n"
        "• https://vk.com/video...\n"
        "• https://m.vk.com/video..."
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    await message.answer(
        "ℹ️ Как пользоваться:\n\n"
        "1. Найди видео в VK\n"
        "2. Скопируй ссылку на видео\n"
        "3. Отправь ссылку мне\n"
        "4. Жди загрузки!\n\n"
        "⚡ Бот загружает видео в максимальном доступном качестве"
    )


@dp.message()
async def handle_message(message: types.Message):
    """Обработчик всех сообщений с ссылками на видео"""
    text = message.text
    
    # Проверяем, что это ссылка на VK
    if not text or ('vk.com' not in text and 'vkvideo.ru' not in text):
        await message.answer("⚠️ Пожалуйста, отправь ссылку на видео из VK")
        return
    
    # Отправляем сообщение о начале загрузки
    status_msg = await message.answer("⏳ Загружаю видео... Это может занять некоторое время.")
    
    try:
        # Скачиваем видео
        filepath, title = download_vk_video(text)
        
        # Проверяем размер файла
        file_size = os.path.getsize(filepath)
        file_size_mb = file_size / (1024 * 1024)
        
        # Telegram поддерживает файлы до 50 МБ для ботов (или 2 ГБ с Premium)
        if file_size_mb > 2000:
            await status_msg.edit_text(
                f"❌ Файл слишком большой ({file_size_mb:.1f} МБ).\n"
                f"Telegram ограничивает размер файлов до 2 ГБ."
            )
            os.remove(filepath)
            return
        
        await status_msg.edit_text(f"📤 Отправляю видео ({file_size_mb:.1f} МБ)...")
        
        # Отправляем видео
        video_file = FSInputFile(filepath)
        await message.answer_video(
            video=video_file,
            caption=f"🎬 {title}",
            supports_streaming=True
        )
        
        # Удаляем статусное сообщение
        await status_msg.delete()
        
        # Удаляем загруженный файл
        os.remove(filepath)
        
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        await status_msg.edit_text(
            f"❌ Произошла ошибка при загрузке видео.\n"
            f"Убедитесь, что:\n"
            f"• Ссылка корректная\n"
            f"• Видео доступно для просмотра\n"
            f"• Видео не удалено"
        )


async def on_startup(app):
    """Действия при запуске бота"""
    # Устанавливаем webhook
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info(f"Webhook установлен: {webhook_url}")


async def on_shutdown(app):
    """Действия при остановке бота"""
    await bot.delete_webhook()
    logger.info("Webhook удален")


async def health_check(request):
    """Health check endpoint для Render"""
    return web.Response(text="OK", status=200)


def main():
    """Запуск бота"""
    # Создаем aiohttp приложение
    app = web.Application()
    
    # Health check endpoint
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    # Webhook handler
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)
    
    # События запуска/остановки
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # Настройка приложения
    setup_application(app, dp, bot=bot)
    
    # Запуск веб-сервера
    logger.info(f"Бот запущен на порту {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
