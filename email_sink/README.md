# Email Sink Service

The Email Sink service monitors Gmail accounts for incoming alerts and routes them to internal API endpoints for processing and storage.

## Overview

This service implements a configurable email monitoring system that:

1. **Connects to Gmail via IMAP** - Securely logs into a dedicated Gmail account
2. **Polls for new emails** - Checks for unread messages every minute (configurable)
3. **Filters by sender patterns** - Supports multiple configurable sender patterns for flexible email filtering
4. **Parses email content** - Extracts structured data from raw email messages
5. **Routes to API endpoints** - POSTs parsed alerts to internal endpoints
6. **Stores persistently** - Alerts are saved to JSON files for later retrieval

## Architecture

```
Gmail (IMAP)
   ↓ (poll every minute)
Dockerized Email Sink Service
   ↓
Filters by configurable sender patterns (e.g. "alerts@, @transit.gov, notifications@weather.gov")
   ↓
Parses email content
   ↓
POST to internal endpoint (/commute_alert)
   ↓
Writes structured alert to persistent JSON storage
```

## Setup

### 1. Gmail Configuration

**Enable IMAP in Gmail:**
- Go to Gmail → Settings → See all settings → Forwarding and POP/IMAP
- Enable IMAP access

**Create App Password (if 2FA is enabled):**
- Visit: https://myaccount.google.com/apppasswords
- Generate a password for "Mail" → "Other (Custom name)"
- Save the generated password securely

### 2. Environment Configuration

Add the following to your `.env` file:

```bash
# Email Sink Configuration
EMAIL_SINK_ENABLED=true
EMAIL_ADDRESS=your-monitoring-email@gmail.com
EMAIL_PASSWORD=your-app-password-or-regular-password
EMAIL_IMAP_SERVER=imap.gmail.com
EMAIL_POLL_INTERVAL=60
EMAIL_SENDER_PATTERNS=alerts@,@transit.gov,notifications@weather.gov
STORAGE_PATH=storage
```

### 3. Deploy with Docker Compose

The service is already configured in `docker-compose.yml`. Simply run:

```bash
docker-compose up email-sink
```

Or to run all services:

```bash
docker-compose up
```

## Configuration

### Email Sender Patterns

The service uses **comma-separated sender patterns** for flexible email filtering. This supports multiple patterns and substring matching:

#### Pattern Examples:

1. **Partial email patterns**: `alerts@` - matches any sender containing "alerts@"
2. **Domain patterns**: `@transit.gov` - matches any sender from the transit.gov domain
3. **Specific addresses**: `notifications@weather.gov` - matches that specific email address
4. **Multiple patterns**: `alerts@,@transit.gov,notifications@weather.gov` - monitors all patterns

#### Configuration in Environment:

```bash
# Single pattern
EMAIL_SENDER_PATTERNS=alerts@

# Multiple patterns (comma-separated)
EMAIL_SENDER_PATTERNS=alerts@,@transit.gov,notifications@weather.gov,traffic@city.gov

# Mix of pattern types
EMAIL_SENDER_PATTERNS=alerts@,@weatherservice.gov,emergency@,notifications@transit.local
```

#### How Pattern Matching Works:

- **Substring matching**: All patterns use substring matching, so:
  - `alerts@` matches `alerts@transit.gov`, `alerts@weather.gov`, etc.
  - `@domain.com` matches `any-sender@domain.com`
  - `notifications@` matches `notifications@any-domain.com`

- **Multiple configs**: Each pattern creates a separate monitoring configuration
- **Same endpoint**: Currently all patterns route to `/commute_alert`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_SINK_ENABLED` | `false` | Enable/disable the email monitoring service |
| `EMAIL_ADDRESS` | `""` | Gmail address for monitoring |
| `EMAIL_PASSWORD` | `""` | Gmail app password or regular password |
| `EMAIL_IMAP_SERVER` | `imap.gmail.com` | IMAP server hostname |
| `EMAIL_POLL_INTERVAL` | `60` | Polling interval in seconds |
| `EMAIL_SENDER_PATTERNS` | `alerts@` | Comma-separated sender patterns for filtering |
| `STORAGE_PATH` | `storage` | Directory for persistent JSON storage |

## API Endpoints

### POST /commute_alert

Receives and stores commute alerts from the email sink service.

**Request Body:**
```json
{
  "uid": "12345",
  "subject": "Traffic Alert: Heavy delays on I-95",
  "body": "Due to an accident, expect delays of 30+ minutes...",
  "sender": "alerts@transit.local.gov",
  "date": "2025-01-15T08:30:00Z",
  "alert_type": "email"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Alert stored successfully",
  "alert_id": "alert_1_12345"
}
```

## Storage

Alerts are stored in JSON format in the `storage/commute_alerts.json` file:

```json
[
  {
    "id": "alert_1_12345",
    "uid": "12345",
    "subject": "Traffic Alert: Heavy delays on I-95",
    "body": "Due to an accident, expect delays...",
    "sender": "alerts@transit.local.gov",
    "received_date": "2025-01-15T08:30:00Z",
    "stored_date": "2025-01-15T08:30:15Z",
    "alert_type": "email"
  }
]
```

## Examples

### Example 1: Transit Authority Alerts
```bash
EMAIL_SENDER_PATTERNS=alerts@transit.gov,notifications@metro.city.gov
```
This monitors:
- Any email from addresses containing "alerts@transit.gov"
- Any email from the metro.city.gov domain

### Example 2: Weather and Emergency Alerts
```bash
EMAIL_SENDER_PATTERNS=@weather.gov,emergency@,alerts@emergency
```
This monitors:
- Any email from weather.gov domain
- Any email with "emergency@" in the sender
- Any email with "alerts@emergency" in the sender

### Example 3: Multiple Services
```bash
EMAIL_SENDER_PATTERNS=alerts@,notifications@,@alerting.transit.gov,traffic@city.local
```
This monitors:
- Any "alerts@" emails
- Any "notifications@" emails  
- Any emails from alerting.transit.gov domain
- Specific address traffic@city.local

## Development

### Running Locally

```bash
# Install dependencies
uv sync

# Run the service directly
uv run python -m email_sink.main

# Or run with Docker
docker-compose up email-sink
```

### Testing

```bash
# Run all email_sink tests
uv run pytest tests/unit/email_sink/ -v

# Run specific test module
uv run pytest tests/unit/email_sink/test_monitor.py -v
```

### Code Quality

```bash
# Run linting
make lint

# Run all tests
make test
```

## Security Considerations

- **App Passwords**: Use Gmail app passwords instead of regular passwords when 2FA is enabled
- **Environment Variables**: Never commit actual credentials to version control
- **IMAP Security**: Uses SSL/TLS for secure IMAP connections
- **Authentication**: API endpoints require X-Token authentication
- **Pattern Security**: Be careful with broad patterns like `@` which would match all emails

## Troubleshooting

### Common Issues

1. **"Login failed"**: Check email address and password/app password
2. **"IMAP not enabled"**: Enable IMAP in Gmail settings
3. **"No emails found"**: Verify sender patterns match actual email senders
4. **"Service not starting"**: Check that `EMAIL_SINK_ENABLED=true` in environment
5. **"No patterns configured"**: Ensure `EMAIL_SENDER_PATTERNS` is set with valid patterns

### Testing Sender Patterns

To test if your patterns work correctly:

1. **Check logs**: The service logs which patterns are loaded on startup
2. **Send test emails**: Send emails from addresses matching your patterns
3. **Verify matching**: Check that the IMAP substring matching works as expected

### Logs

The service uses structured logging. Check Docker logs:

```bash
docker-compose logs email-sink
```

Look for log messages about pattern loading:
```
INFO: Loaded 3 email sink configurations: ['alerts@', '@transit.gov', 'notifications@weather.gov']
```

## Extending the Service

### Adding New Alert Types

To route different patterns to different endpoints:

1. Modify `_load_email_configs()` in `monitor.py`:

```python
def _load_email_configs(self) -> None:
    """Load email sink configurations with custom routing."""
    patterns = [pattern.strip() for pattern in config.email_sender_patterns.split(',')]
    
    for pattern in patterns:
        # Route based on pattern content
        if 'weather' in pattern.lower():
            endpoint = '/weather_alert'
        elif 'traffic' in pattern.lower() or 'transit' in pattern.lower():
            endpoint = '/commute_alert'
        else:
            endpoint = '/general_alert'
            
        self.email_configs.append(
            EmailSinkConfig(
                sender_pattern=pattern,
                endpoint=endpoint,
                description=f"Alerts from pattern: {pattern}"
            )
        )
```

2. Add corresponding API endpoints in `main_router.py`
3. Add tests for new functionality

### Custom Email Parsing

The `EmailParser` can be extended for domain-specific parsing based on sender patterns:

```python
@staticmethod
def extract_alert_info(alert: EmailAlert) -> dict:
    """Extract information based on sender pattern."""
    if 'weather' in alert.sender.lower():
        return EmailParser.extract_weather_info(alert)
    elif 'transit' in alert.sender.lower():
        return EmailParser.extract_commute_info(alert)
    else:
        return EmailParser.extract_general_info(alert)
``` 