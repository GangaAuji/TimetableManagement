"""Security helpers for mobile API authentication and rate limiting."""

import hashlib
import hmac
import time
from flask import current_app, g, jsonify, request

from config import Config
from database import get_db_connection


def _json_error(message, status=400):
    return jsonify({"success": False, "error": message}), status


def _extract_bearer_or_header():
    provided = request.headers.get("X-Mobile-Api-Key", "")
    if provided:
        return provided.strip()

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return ""


def _parse_timestamp(raw_timestamp):
    try:
        return int(str(raw_timestamp).strip())
    except Exception:
        return None


def _build_string_to_sign(timestamp, nonce, body_hash):
    return "\n".join([
        request.method.upper(),
        request.path,
        str(timestamp),
        nonce,
        body_hash,
    ])


def _build_string_to_sign_candidates(timestamp, nonce, body_hash):
    candidates = [_build_string_to_sign(timestamp, nonce, body_hash)]

    raw_query = request.query_string.decode("utf-8", errors="ignore")
    if raw_query:
        candidates.append("\n".join([
            request.method.upper(),
            f"{request.path}?{raw_query}",
            str(timestamp),
            nonce,
            body_hash,
        ]))

    return candidates


def _verify_device_signature(cursor, device_id, timestamp, nonce, signature):
    cursor.execute(
        """
        SELECT id, device_id, device_name, owner_user_id, api_key_secret, is_active,
               COALESCE(rate_limit_per_minute, %s) AS rate_limit_per_minute
        FROM mobile_devices
        WHERE device_id = %s
        LIMIT 1
        """,
        (Config.MOBILE_SYNC_DEFAULT_RATE_LIMIT_PER_MINUTE, device_id),
    )
    device = cursor.fetchone()

    if not device:
        return None, _json_error("Unknown mobile device", 401)

    if int(device.get("is_active", 0)) != 1:
        return None, _json_error("Mobile device is disabled", 403)

    body_bytes = request.get_data(cache=True) or b""
    body_hash = hashlib.sha256(body_bytes).hexdigest()

    secret = str(device.get("api_key_secret") or "")
    valid_signature = False
    for string_to_sign in _build_string_to_sign_candidates(timestamp, nonce, body_hash):
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(expected_signature, signature):
            valid_signature = True
            break

    if not valid_signature:
        return None, _json_error("Invalid signature", 401)

    return device, None


def _enforce_rate_limit_and_nonce(cursor, device, nonce):
    cursor.execute(
        """
        SELECT COUNT(*) AS request_count
        FROM mobile_request_nonces
        WHERE device_id = %s
          AND created_at >= (UTC_TIMESTAMP() - INTERVAL 1 MINUTE)
        """,
        (device["device_id"],),
    )
    count_row = cursor.fetchone() or {"request_count": 0}
    request_count = int(count_row.get("request_count", 0))

    limit_value = int(device.get("rate_limit_per_minute") or Config.MOBILE_SYNC_DEFAULT_RATE_LIMIT_PER_MINUTE)
    if request.path.startswith("/mobile-sync/v1/attendance/sync"):
        multiplier = int(getattr(Config, "MOBILE_SYNC_ATTENDANCE_RATE_LIMIT_MULTIPLIER", 1) or 1)
        if multiplier > 1:
            limit_value *= multiplier

    if request_count >= limit_value:
        return _json_error(
            f"Rate limit exceeded ({request_count}/{limit_value} per minute). Retry in about 60 seconds.",
            429,
        )

    try:
        cursor.execute(
            "INSERT INTO mobile_request_nonces (device_id, nonce) VALUES (%s, %s)",
            (device["device_id"], nonce),
        )
    except Exception:
        return _json_error("Replay detected: nonce already used", 409)

    cursor.execute(
        "UPDATE mobile_devices SET last_used_at = UTC_TIMESTAMP() WHERE id = %s",
        (device["id"],),
    )

    return None


def authenticate_mobile_request(allow_legacy_api_key=False):
    """Authenticate request using device signatures, with optional legacy fallback."""
    device_id = str(request.headers.get("X-Mobile-Device-Id", "")).strip()
    timestamp_raw = request.headers.get("X-Mobile-Timestamp")
    nonce = str(request.headers.get("X-Mobile-Nonce", "")).strip()
    signature = str(request.headers.get("X-Mobile-Signature", "")).strip().lower()

    has_signature_headers = bool(device_id and timestamp_raw and nonce and signature)

    if not has_signature_headers:
        if not allow_legacy_api_key:
            return _json_error(
                "Signed headers required: X-Mobile-Device-Id, X-Mobile-Timestamp, X-Mobile-Nonce, X-Mobile-Signature",
                401,
            )

        api_key = _extract_bearer_or_header()
        configured = str(Config.MOBILE_SYNC_API_KEY or "")
        if not configured:
            current_app.logger.error("MOBILE_SYNC_API_KEY is not configured.")
            return _json_error("Mobile sync is not configured on server", 503)

        if not api_key or not hmac.compare_digest(api_key, configured):
            return _json_error("Unauthorized", 401)

        g.mobile_auth = {
            "mode": "legacy_api_key",
            "device_id": None,
            "owner_user_id": None,
            "rate_limit_per_minute": None,
        }
        return None

    timestamp = _parse_timestamp(timestamp_raw)
    if timestamp is None:
        return _json_error("Invalid X-Mobile-Timestamp", 400)

    now_utc = int(time.time())
    allowed_skew = int(Config.MOBILE_SYNC_SIGNATURE_WINDOW_SECONDS)
    if abs(now_utc - timestamp) > allowed_skew:
        return _json_error("Request timestamp outside allowed window", 401)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        device, verify_error = _verify_device_signature(cursor, device_id, timestamp, nonce, signature)
        if verify_error:
            connection.rollback()
            return verify_error

        nonce_error = _enforce_rate_limit_and_nonce(cursor, device, nonce)
        if nonce_error:
            connection.rollback()
            return nonce_error

        connection.commit()

        g.mobile_auth = {
            "mode": "device_signature",
            "device_id": device["device_id"],
            "owner_user_id": device.get("owner_user_id"),
            "rate_limit_per_minute": int(device.get("rate_limit_per_minute") or 0),
        }
        return None
    except Exception as e:
        connection.rollback()
        current_app.logger.error("Mobile auth failed: %s", str(e))
        message = str(e).lower()
        if "mobile_devices" in message or "mobile_request_nonces" in message:
            return _json_error("Mobile API security tables are missing. Run mobile security migration.", 503)
        return _json_error("Mobile authentication failed", 500)
    finally:
        cursor.close()
        connection.close()
