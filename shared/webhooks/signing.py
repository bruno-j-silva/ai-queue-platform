"""Canonical webhook HMAC-SHA256 signatures."""

import hashlib
import hmac


def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    message = str(timestamp).encode() + b"." + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, timestamp: int, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, timestamp, body), signature)


def build_headers(
    delivery_id: str,
    attempt: int,
    timestamp: int,
    signature: str,
) -> dict[str, str]:
    return {
        "X-Delivery-Id": delivery_id,
        "X-Timestamp": str(timestamp),
        "X-Attempt": str(attempt),
        "X-Signature": signature,
        "Content-Type": "application/json",
    }
