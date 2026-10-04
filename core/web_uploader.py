"""
🌐 Telegram Web App / Mini App Uploader
Дозволяє завантажувати відео будь-якого розміру (до 500 МБ)
прямо всередині Telegram через нативне вікно Web App без жодних лімітів!
"""
import os
import html
import json
import logging
from pathlib import Path
from aiohttp import web
from config import DOWNLOADS_DIR, BASE_DIR
from core.content_type import ContentType

logger = logging.getLogger("web_uploader")
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

HTML_PAGE = """<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Швидке завантаження відео</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--tg-theme-bg-color, #0f172a);
      color: var(--tg-theme-text-color, #f8fafc);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
      text-align: center;
    }
    .card {
      background: rgba(30, 41, 59, 0.7);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 24px;
      padding: 32px 24px;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.4);
    }
    .icon { font-size: 54px; margin-bottom: 16px; }
    h2 { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
    p { font-size: 14px; color: #94a3b8; margin-bottom: 24px; line-height: 1.5; }
    .drop-zone {
      border: 2px dashed #38bdf8;
      border-radius: 18px;
      padding: 32px 16px;
      cursor: pointer;
      background: rgba(56, 189, 248, 0.05);
      transition: all 0.2s ease;
      margin-bottom: 20px;
    }
    .drop-zone:hover {
      background: rgba(56, 189, 248, 0.12);
      border-color: #7dd3fc;
    }
    .drop-zone span {
      display: block;
      font-weight: 600;
      color: #38bdf8;
      font-size: 15px;
    }
    .drop-zone small {
      display: block;
      color: #64748b;
      font-size: 12px;
      margin-top: 6px;
    }
    input[type="file"] { display: none; }
    .progress-bar {
      width: 100%;
      height: 8px;
      background: #1e293b;
      border-radius: 4px;
      overflow: hidden;
      margin-top: 16px;
      display: none;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #38bdf8, #818cf8);
      transition: width 0.2s ease;
    }
    .status {
      margin-top: 16px;
      font-size: 14px;
      font-weight: 500;
      color: #e2e8f0;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🚀</div>
    <h2>Завантаження відео без лімітів</h2>
    <p>Оминає ліміт Telegram 20 МБ. Підтримує важкі 4K ролики до 500 МБ.</p>

    <div class="drop-zone" onclick="document.getElementById('fileInput').click()">
      <span>📁 Оберіть або перетягніть відео</span>
      <small>MP4, MOV, WebM (до 500 МБ)</small>
    </div>

    <input type="file" id="fileInput" accept="video/*" onchange="uploadFile(this.files[0])">

    <div class="progress-bar" id="progressBar">
      <div class="progress-fill" id="progressFill"></div>
    </div>
    <div class="status" id="statusText"></div>
  </div>

  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
    }

    function uploadFile(file) {
      if (!file) return;

      const pBar = document.getElementById('progressBar');
      const pFill = document.getElementById('progressFill');
      const status = document.getElementById('statusText');

      pBar.style.display = 'block';
      status.innerText = `Завантажуємо ${file.name} (${(file.size / (1024*1024)).toFixed(1)} МБ)...`;

      const formData = new FormData();
      formData.append('video', file);

      // Отримуємо telegram user id якщо відкрито у WebApp
      const userId = tg?.initDataUnsafe?.user?.id || '';
      formData.append('user_id', userId);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload', true);

      xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
          const percent = (e.loaded / e.total) * 100;
          pFill.style.width = percent + '%';
          status.innerText = `Завантаження: ${Math.round(percent)}%...`;
        }
      };

      xhr.onload = function() {
        if (xhr.status === 200) {
          status.innerText = "🎉 Відео завантажено! Бот уже готує опис та публікацію...";
          pFill.style.width = '100%';
          setTimeout(() => {
            if (tg) { tg.close(); }
          }, 1800);
        } else {
          status.innerText = "❌ Помилка: " + xhr.responseText;
        }
      };

      xhr.onerror = function() {
        status.innerText = "❌ Помилка з'єднання з сервером";
      };

      xhr.send(formData);
    }
  </script>
</body>
</html>
"""

async def handle_index(request: web.Request) -> web.Response:
    return web.Response(text=HTML_PAGE, content_type="text/html")


async def handle_upload(request: web.Request) -> web.Response:
    reader = await request.multipart()
    user_id = None
    saved_path = None

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "user_id":
            val = await part.text()
            if val and val.isdigit():
                user_id = int(val)
        elif part.name == "video":
            filename = part.filename or "uploaded_video.mp4"
            clean_name = f"web_{user_id or 'anon'}_{filename}"
            target = DOWNLOADS_DIR / clean_name
            with open(target, "wb") as f:
                while True:
                    chunk = await part.read_chunk(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            saved_path = str(target)

    if not saved_path:
        return web.Response(text="Файл не отримано", status=400)

    logger.info(f"✅ WebApp отримав відео: {saved_path} (user_id={user_id})")

    # Якщо user_id відомий — повідомляємо бота через фоновий процес
    bot = request.app.get("bot")
    if bot and user_id:
        import asyncio
        from services.automations.auto_poster import auto_poster
        from bot.handlers import send_prepared_preview

        async def process_and_notify():
            try:
                status_msg = await bot.send_message(
                    user_id,
                    "🧠 <b>Відео отримано без лімітів!</b> Перевіряємо якість, Gemini 3.5 створює описи...",
                    parse_mode="HTML"
                )
                data = auto_poster.process_incoming_video(saved_path)
                # Відправляємо прев'ю користувачу
                class FakeMessage:
                    def __init__(self, uid, b):
                        self.from_user = type('User', (), {'id': uid})()
                        self.chat = type('Chat', (), {'id': uid})()
                        self.bot = b
                    async def answer(self, *args, **kwargs):
                        return await self.bot.send_message(self.chat.id, *args, **kwargs)

                fake_msg = FakeMessage(user_id, bot)
                await send_prepared_preview(fake_msg, status_msg, data)
            except Exception as pe:
                logger.error(f"Помилка обробки завантаженого через WebApp відео: {pe}")
                try:
                    await bot.send_message(user_id, f"❌ Помилка обробки відео: {pe}")
                except Exception:
                    pass

        asyncio.create_task(process_and_notify())

    return web.json_response({"status": "ok", "path": saved_path})


def create_web_uploader_app(bot=None) -> web.Application:
    app = web.Application(client_max_size=500 * 1024 * 1024)  # 500 MB max file
    app["bot"] = bot
    app.router.add_get("/", handle_index)
    app.router.add_get("/upload", handle_index)
    app.router.add_post("/api/upload", handle_upload)
    return app
