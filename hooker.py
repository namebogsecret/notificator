import os
import asyncio
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from collections import defaultdict
from time import time
import aiohttp
from aiohttp import web
import aiosqlite
from dotenv import load_dotenv
import ssl

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('notificator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration constants
API_KEY = os.getenv('API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SSL_CERT_PATH = os.getenv('SSL_CERT_PATH', '/root/keys/cert.pem')
SSL_KEY_PATH = os.getenv('SSL_KEY_PATH', '/root/keys/key_no_password.pem')
DB_NAME = os.getenv('DB_NAME', 'notifications.db')
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '5000'))

# Validation constants
MAX_MESSAGE_LENGTH = 4096  # Telegram message limit
MAX_SERVICE_LENGTH = 100
MAX_EVENT_LENGTH = 100
MAX_FIELD_LENGTH = 1000

# Rate limiting configuration
RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', '10'))
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))  # seconds

# Validate required environment variables
if not all([API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logger.error("Missing required environment variables: API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
    raise ValueError("Not all required environment variables are set. Please check API_KEY, TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID.")

# Simple in-memory rate limiter
rate_limit_store: Dict[str, list] = defaultdict(list)


def check_rate_limit(ip: str) -> bool:
    """
    Check if the IP address has exceeded the rate limit.

    Args:
        ip: The IP address to check

    Returns:
        True if within rate limit, False otherwise
    """
    now = time()
    # Clean old entries
    rate_limit_store[ip] = [req_time for req_time in rate_limit_store[ip]
                            if now - req_time < RATE_LIMIT_WINDOW]

    # Check if limit exceeded
    if len(rate_limit_store[ip]) >= RATE_LIMIT_REQUESTS:
        logger.warning(f"Rate limit exceeded for IP: {ip}")
        return False

    # Add current request
    rate_limit_store[ip].append(now)
    return True


async def send_to_telegram(message: str, max_retries: int = 3) -> bool:
    """
    Send a message to Telegram with retry logic.

    Args:
        message: The message to send
        max_retries: Maximum number of retry attempts

    Returns:
        True if message was sent successfully, False otherwise
    """
    # Truncate message if too long
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[:MAX_MESSAGE_LENGTH - 3] + "..."
        logger.warning(f"Message truncated to {MAX_MESSAGE_LENGTH} characters")

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    params = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}

    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=params) as response:
                    if response.status == 200:
                        logger.info('Message successfully sent to Telegram')
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f'Telegram API error (status {response.status}): {error_text}')
        except aiohttp.ClientError as e:
            logger.error(f'Attempt {attempt + 1}/{max_retries} failed: {e}')
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f'Unexpected error sending to Telegram: {e}')
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)

    logger.error(f'Failed to send message to Telegram after {max_retries} attempts')
    return False


async def get_db_connection() -> aiosqlite.Connection:
    """
    Create and return an asynchronous connection to the SQLite database.

    Returns:
        aiosqlite.Connection: Database connection object
    """
    conn = await aiosqlite.connect(DB_NAME)
    conn.row_factory = aiosqlite.Row
    return conn


async def create_table() -> None:
    """
    Create the notifications table and indexes if they don't exist.
    """
    try:
        conn = await get_db_connection()

        # Create table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT,
                event TEXT,
                error BOOLEAN,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes for better query performance
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_service ON notifications(service)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON notifications(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_error ON notifications(error)')

        await conn.commit()
        await conn.close()
        logger.info("Database table and indexes created successfully")
    except aiosqlite.Error as e:
        logger.error(f"Database error during table creation: {e}")
        raise


def validate_notification_data(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate notification data.

    Args:
        data: The notification data to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Data must be a JSON object"

    # Check for required fields
    if 'service' not in data or 'message' not in data:
        return False, "Missing required fields: 'service' and 'message'"

    # Validate field types and lengths
    if not isinstance(data.get('service'), str):
        return False, "Field 'service' must be a string"

    if len(data.get('service', '')) > MAX_SERVICE_LENGTH:
        return False, f"Field 'service' exceeds maximum length of {MAX_SERVICE_LENGTH}"

    if 'event' in data:
        if not isinstance(data['event'], str):
            return False, "Field 'event' must be a string"
        if len(data['event']) > MAX_EVENT_LENGTH:
            return False, f"Field 'event' exceeds maximum length of {MAX_EVENT_LENGTH}"

    if not isinstance(data.get('message'), str):
        return False, "Field 'message' must be a string"

    if len(data.get('message', '')) > MAX_FIELD_LENGTH:
        return False, f"Field 'message' exceeds maximum length of {MAX_FIELD_LENGTH}"

    if 'error' in data and not isinstance(data['error'], bool):
        return False, "Field 'error' must be a boolean"

    return True, None


async def webhook(request: web.Request) -> web.Response:
    """
    Endpoint for receiving notifications from various services with authentication.

    Args:
        request: The incoming HTTP request

    Returns:
        web.Response: JSON response
    """
    try:
        # Get client IP for rate limiting
        client_ip = request.remote or 'unknown'

        # Check rate limit
        if not check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return web.json_response(
                {"error": "Rate limit exceeded. Please try again later."},
                status=429
            )

        # API key authentication with timing attack protection
        api_key = request.headers.get('API-Key', '')
        if not api_key or not secrets.compare_digest(api_key, API_KEY):
            logger.warning(f"Unauthorized access attempt from IP: {client_ip}")
            # Don't send Telegram notification for every failed auth attempt
            # to prevent spam/DoS via notifications
            return web.json_response({"error": "Unauthorized"}, status=401)

        # Parse and validate request data
        try:
            data = await request.json()
        except Exception as e:
            logger.error(f"Invalid JSON from {client_ip}: {e}")
            return web.json_response(
                {"error": "Invalid JSON format"},
                status=400
            )

        # Validate notification data
        is_valid, error_message = validate_notification_data(data)
        if not is_valid:
            logger.error(f"Validation error from {client_ip}: {error_message}")
            return web.json_response(
                {"error": error_message},
                status=400
            )

        # Save to database with UTC timestamp
        try:
            conn = await get_db_connection()
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            await conn.execute(
                'INSERT INTO notifications (service, event, error, message, created_at) VALUES (?, ?, ?, ?, ?)',
                (
                    data.get('service'),
                    data.get('event', ''),
                    data.get('error', False),
                    data.get('message', ''),
                    current_time
                )
            )
            await conn.commit()
            await conn.close()
            logger.info(f"Notification saved from service: {data.get('service')}")
        except aiosqlite.Error as e:
            logger.error(f"Database error: {e}")
            return web.json_response(
                {"error": "Database error"},
                status=500
            )

        # Send notification to Telegram
        telegram_message = f"📢 {data.get('service')}: {data.get('message')}"
        if data.get('error'):
            telegram_message = f"❌ {data.get('service')}: {data.get('message')}"

        await send_to_telegram(telegram_message)

        return web.json_response({"success": True}, status=200)

    except aiohttp.ClientError as e:
        logger.error(f"HTTP client error: {e}")
        return web.json_response(
            {"error": "Service unavailable"},
            status=503
        )
    except Exception as e:
        logger.error(f"Unexpected error in webhook: {e}", exc_info=True)
        return web.json_response(
            {"error": "Internal Server Error"},
            status=500
        )


async def init_app() -> web.Application:
    """
    Initialize the application.

    Returns:
        Configured web application
    """
    app = web.Application()
    app.router.add_post('/webhook', webhook)
    return app


if __name__ == '__main__':
    try:
        # Create database table
        loop = asyncio.get_event_loop()
        loop.run_until_complete(create_table())

        # Setup SSL context
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

        try:
            ssl_context.load_cert_chain(SSL_CERT_PATH, SSL_KEY_PATH)
            logger.info(f"SSL certificates loaded from {SSL_CERT_PATH}")
        except FileNotFoundError as e:
            logger.error(f"SSL certificate files not found: {e}")
            logger.info("Starting server without SSL (HTTP only)")
            ssl_context = None

        # Initialize and run app
        app = loop.run_until_complete(init_app())

        logger.info(f"Starting server on {HOST}:{PORT}")
        web.run_app(app, ssl_context=ssl_context, port=PORT, host=HOST)

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        exit(1)
