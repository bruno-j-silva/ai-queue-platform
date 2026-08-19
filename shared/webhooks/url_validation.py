"""Webhook URL validation with SSRF protections."""

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeWebhookUrlError(ValueError):
    """Raised when a callback target is unsafe."""


def validate_webhook_url(url: str, *, allow_private: bool = False) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeWebhookUrlError("Webhook URL must use HTTPS")
    if parsed.username or parsed.password or parsed.fragment:
        raise UnsafeWebhookUrlError("Webhook URL cannot contain credentials or fragments")

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise UnsafeWebhookUrlError("Webhook hostname could not be resolved") from exc

    if not allow_private:
        for value in addresses:
            address = ipaddress.ip_address(value)
            if not address.is_global:
                raise UnsafeWebhookUrlError("Webhook URL resolves to a non-public address")
    return url
