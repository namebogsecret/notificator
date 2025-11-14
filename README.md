# Notificator

A secure webhook server for receiving notifications from various services and forwarding them to Telegram.

## Features

- **Secure Authentication**: API key-based authentication with timing attack protection
- **Rate Limiting**: Built-in rate limiting to prevent DoS attacks
- **Retry Logic**: Automatic retry mechanism for Telegram message delivery
- **Data Validation**: Comprehensive input validation and sanitization
- **Structured Logging**: Detailed logging to file and console
- **SSL/TLS Support**: HTTPS support with configurable SSL certificates
- **Database Storage**: SQLite database for notification history with optimized indexes
- **Type Safety**: Full type hints for better code quality

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd notificator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Configuration

### Required Environment Variables

- `API_KEY`: Secret key for webhook authentication
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token (get it from @BotFather)
- `TELEGRAM_CHAT_ID`: Telegram chat ID where notifications will be sent

### Optional Environment Variables

- `SSL_CERT_PATH`: Path to SSL certificate (default: `/root/keys/cert.pem`)
- `SSL_KEY_PATH`: Path to SSL private key (default: `/root/keys/key_no_password.pem`)
- `HOST`: Server host (default: `0.0.0.0`)
- `PORT`: Server port (default: `5000`)
- `DB_NAME`: Database file name (default: `notifications.db`)
- `RATE_LIMIT_REQUESTS`: Max requests per window (default: `10`)
- `RATE_LIMIT_WINDOW`: Rate limit window in seconds (default: `60`)

## Usage

### Starting the Server

```bash
python hooker.py
```

The server will start on the configured host and port (default: `https://0.0.0.0:5000`).

### Sending Notifications

Send a POST request to `/webhook` with the following headers and JSON body:

**Headers:**
```
API-Key: your_secret_api_key
Content-Type: application/json
```

**Body:**
```json
{
  "service": "service-name",
  "event": "event-type",
  "error": false,
  "message": "Your notification message"
}
```

**Required Fields:**
- `service`: Name of the service sending the notification (max 100 chars)
- `message`: Notification message (max 1000 chars)

**Optional Fields:**
- `event`: Event type (max 100 chars)
- `error`: Boolean flag indicating if this is an error notification

### Example with cURL

```bash
curl -X POST https://your-server:5000/webhook \
  -H "API-Key: your_secret_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "service": "MyApp",
    "event": "deployment",
    "error": false,
    "message": "Successfully deployed version 1.0.0"
  }'
```

### Example Response

**Success (200):**
```json
{
  "success": true
}
```

**Error (401 - Unauthorized):**
```json
{
  "error": "Unauthorized"
}
```

**Error (429 - Rate Limit):**
```json
{
  "error": "Rate limit exceeded. Please try again later."
}
```

**Error (400 - Validation):**
```json
{
  "error": "Missing required fields: 'service' and 'message'"
}
```

## Security Features

1. **API Key Authentication**: All requests must include valid API key
2. **Timing Attack Protection**: Uses `secrets.compare_digest()` for key comparison
3. **Rate Limiting**: Configurable rate limiting per IP address
4. **Input Validation**: Strict validation of all input fields
5. **Length Limits**: Maximum length enforcement on all text fields
6. **SSL/TLS**: Support for HTTPS encryption
7. **Structured Logging**: Security events are logged for audit

## Database Schema

The application creates a SQLite database with the following schema:

```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT,
    event TEXT,
    error BOOLEAN,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_service ON notifications(service);
CREATE INDEX idx_created_at ON notifications(created_at);
CREATE INDEX idx_error ON notifications(error);
```

## Logging

Logs are written to:
- `notificator.log` (file)
- Console (stdout)

Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

## Error Handling

The application handles various error scenarios:
- Network errors with Telegram API (automatic retry with exponential backoff)
- Database errors (proper error messages and status codes)
- Invalid JSON (400 Bad Request)
- Missing or invalid fields (400 Bad Request)
- Rate limit exceeded (429 Too Many Requests)
- Unauthorized access (401 Unauthorized)

## Production Recommendations

1. Use strong, randomly generated API keys
2. Enable SSL/TLS with valid certificates
3. Configure appropriate rate limits
4. Monitor the log file for security events
5. Regularly backup the notifications database
6. Run behind a reverse proxy (e.g., nginx)
7. Use environment-specific configuration
8. Set up log rotation for `notificator.log`

## Troubleshooting

### Server won't start

1. Check that all required environment variables are set
2. Verify SSL certificate paths if using HTTPS
3. Ensure port is not already in use
4. Check logs in `notificator.log`

### Notifications not received in Telegram

1. Verify `TELEGRAM_BOT_TOKEN` is correct
2. Verify `TELEGRAM_CHAT_ID` is correct
3. Check that bot has permission to send messages to the chat
4. Review logs for Telegram API errors

### Rate limit issues

Adjust `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` in your `.env` file.

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
