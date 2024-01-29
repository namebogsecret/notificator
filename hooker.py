import os
import asyncio
from datetime import datetime
import aiohttp
from aiohttp import web
import aiosqlite  # Use aiosqlite for asynchronous SQLite operations
from dotenv import load_dotenv
import ssl

load_dotenv()

API_KEY = os.getenv('API-KEY')
bot_token = os.getenv('TELEGRAM_API')
chat_id = os.getenv('ChAT_ID')

app = web.Application()

async def send_to_telegram(message):
    """ Отправка сообщения в Telegram """
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    params = {'chat_id': chat_id, 'text': message}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=params) as response:
            if response.status == 200:
                print('Сообщение успешно отправлено')
            else:
                print('Ошибка при отправке сообщения')

async def get_db_connection():
    conn = await aiosqlite.connect('notifications.db')  # Use aiosqlite for asynchronous SQLite connection
    conn.row_factory = aiosqlite.Row
    return conn

async def create_table():
    conn = await get_db_connection()
    await conn.execute('CREATE TABLE IF NOT EXISTS notifications (service TEXT, event TEXT, error BOOLEAN, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    await conn.commit()
    await conn.close()

async def webhook(request):
    try:
        """ Endpoint для приема уведомлений от разных сервисов с аутентификацией. """
        # Простая проверка API-ключа для безопасности
        api_key = request.headers.get('API-Key')
        if api_key != API_KEY:
            await send_to_telegram('Попытка подключения к хуку с неверным API-ключом')
            return web.json_response({"error": "Unauthorized"}, status=401)

        data = await request.json()
        if not data:
            await send_to_telegram('Попытка подключения к хуку без данных')
            return web.json_response({"error": "No data provided"}, status=400)

        # Сохранение данных в базу данных
        conn = await get_db_connection()
        await conn.execute('INSERT INTO notifications (service, event, error, message, created_at) VALUES (?, ?, ?, ?, ?)',
                        (data.get('service'), data.get('event'), data.get('error', False), data.get('message', ''), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await conn.commit()
        await conn.close()
        await send_to_telegram(f'- {data.get("service")}: {data.get("message")}')
        return web.json_response({"success": True}, status=200)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        # Вы можете добавить дополнительные действия при ошибке, например, отправку уведомления
        return web.json_response({"error": "Internal Server Error"}, status=500)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(create_table())

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)  # Create an SSL context
    ssl_context.load_cert_chain('/root/keys/cert.pem', '/root/keys/key_no_password.pem')  # Load your SSL certificate and private key

    app.router.add_post('/webhook', webhook)
    web.run_app(app, ssl_context=ssl_context, port=5000, host='0.0.0.0')
    