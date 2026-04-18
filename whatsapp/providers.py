"""
WhatsApp provider for Proto v3 - Twilio.

Configuration in config/settings.py or environment variables:
    TWILIO_ACCOUNT_SID   = 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
    TWILIO_AUTH_TOKEN    = 'your_auth_token'
    WHATSAPP_FROM        = '+14155238886'   # Twilio sandbox or approved number
    WHATSAPP_TEST_NUMBER = '+255712345678'  # your number for testing

Twilio sandbox setup (free testing):
  1. Go to console.twilio.com → Messaging → Try it out → Send a WhatsApp message
  2. From your phone, send "join <sandbox-word>" to the sandbox number
  3. Set WHATSAPP_FROM to the sandbox number shown (e.g. +14155238886)
"""

import requests
import logging
from django.conf import settings

logger = logging.getLogger('proto_v3.whatsapp')

TWILIO_API_URL = 'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'


def _get(key, default=''):
    return getattr(settings, key, None) or default


def _normalise_phone(phone: str) -> str:
    """
    Normalise to E.164 format with leading +.
    0712345678  → +255712345678
    255712...   → +255712...
    """
    if not phone:
        return ''
    p = str(phone).strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not p.startswith('+'):
        if p.startswith('0') and len(p) == 10:
            p = '+255' + p[1:]
        elif p.startswith('255'):
            p = '+' + p
        else:
            p = '+' + p
    return p if p.startswith('+') else ''


def send_whatsapp(to: str, message: str, media: str = None) -> dict:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to:      Recipient phone (any format - auto-normalised to E.164)
        message: Plain text message body
        media:   Optional URL to an image or PDF to attach
                 e.g. 'https://yourserver.com/reports/daily.pdf'

    Returns:
        {'success': bool, 'message_id': str, 'error': str}
    """
    sid      = _get('TWILIO_ACCOUNT_SID')
    token    = _get('TWILIO_AUTH_TOKEN')
    from_num = _get('WHATSAPP_FROM')

    if not sid or not token:
        return {'success': False,
                'error': 'Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in settings.'}
    if not from_num:
        return {'success': False,
                'error': 'Set WHATSAPP_FROM in settings (your Twilio WhatsApp number).'}

    to_e164 = _normalise_phone(to)
    if not to_e164:
        return {'success': False, 'error': f'Invalid phone number: {to}'}

    # Twilio requires whatsapp: prefix
    from_wa = 'whatsapp:' + from_num.lstrip('+').replace('whatsapp:', '')
    if not from_wa.startswith('whatsapp:+'):
        from_wa = 'whatsapp:+' + from_wa.replace('whatsapp:', '')

    to_wa = 'whatsapp:' + to_e164

    payload = {
        'From': from_wa,
        'To':   to_wa,
        'Body': message,
    }
    if media:
        payload['MediaUrl'] = media

    try:
        resp = requests.post(
            TWILIO_API_URL.format(sid=sid),
            data=payload,
            auth=(sid, token),
            timeout=15,
        )
        data = resp.json()

        if resp.status_code in (200, 201):
            logger.info(f"Twilio WA sent to {to_e164}: SID={data.get('sid')}")
            return {
                'success':    True,
                'message_id': data.get('sid', ''),
                'status':     data.get('status', 'queued'),
            }
        else:
            err = data.get('message') or data.get('error_message') or resp.text[:200]
            logger.warning(f"Twilio WA failed for {to_e164}: {err}")
            return {'success': False, 'error': err}

    except requests.Timeout:
        return {'success': False, 'error': 'Request timed out after 15s.'}
    except Exception as e:
        logger.error(f'Twilio WhatsApp error: {e}')
        return {'success': False, 'error': str(e)}


def test_connection() -> dict:
    """Send a test message to WHATSAPP_TEST_NUMBER."""
    num = _get('WHATSAPP_TEST_NUMBER')
    if not num:
        return {'success': False, 'error': 'Set WHATSAPP_TEST_NUMBER in settings.'}
    return send_whatsapp(num, '✅ Proto v3 WhatsApp via Twilio is working correctly!')