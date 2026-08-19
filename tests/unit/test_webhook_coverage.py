"""Unit tests for webhook URL validation."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from shared.webhooks.url_validation import (
    UnsafeWebhookUrlError,
    validate_webhook_url,
)


class TestValidateWebhookUrl:
    def test_rejects_http(self) -> None:
        with pytest.raises(UnsafeWebhookUrlError, match="HTTPS"):
            validate_webhook_url("http://example.com/cb")

    def test_rejects_no_hostname(self) -> None:
        with pytest.raises(UnsafeWebhookUrlError, match="HTTPS"):
            validate_webhook_url("https://")

    def test_rejects_credentials(self) -> None:
        with pytest.raises(UnsafeWebhookUrlError, match="credentials"):
            validate_webhook_url("https://user:pass@example.com/cb")

    def test_rejects_fragment(self) -> None:
        with pytest.raises(UnsafeWebhookUrlError, match="credentials"):
            validate_webhook_url("https://example.com/cb#frag")

    def test_rejects_unresolvable_host(self) -> None:
        with patch(
            "shared.webhooks.url_validation.socket.getaddrinfo",
            side_effect=socket.gaierror("no such host"),
        ):
            with pytest.raises(UnsafeWebhookUrlError, match="could not be resolved"):
                validate_webhook_url("https://no-such-host.invalid/cb")

    def test_rejects_private_ip(self) -> None:
        with patch(
            "shared.webhooks.url_validation.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
        ):
            with pytest.raises(UnsafeWebhookUrlError, match="non-public"):
                validate_webhook_url("https://localhost/cb")

    def test_accepts_global_ip(self) -> None:
        with patch(
            "shared.webhooks.url_validation.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 443))],
        ):
            assert validate_webhook_url("https://example.com/cb") == "https://example.com/cb"

    def test_allow_private_bypasses_check(self) -> None:
        with patch(
            "shared.webhooks.url_validation.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
        ):
            assert validate_webhook_url("https://localhost/cb", allow_private=True) == "https://localhost/cb"
