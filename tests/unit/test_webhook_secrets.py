"""Webhook endpoint secrets are generated once and stored safely."""

import pytest
from cryptography.fernet import Fernet

from shared.webhooks.secrets import (
    SecretDecryptionError,
    decrypt_secret,
    encrypt_secret,
    generate_secret,
    hash_secret,
)


def test_webhook_secret_round_trip_and_hash() -> None:
    encryption_key = Fernet.generate_key().decode()
    secret = generate_secret()
    encrypted = encrypt_secret(secret, encryption_key)

    assert secret.startswith("whsec_")
    assert secret not in encrypted
    assert decrypt_secret(encrypted, encryption_key) == secret
    assert hash_secret(secret) == hash_secret(secret)
    assert hash_secret(secret) != hash_secret(secret + "tampered")


def test_decrypt_with_wrong_key_raises() -> None:
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    encrypted = encrypt_secret("whsec_test", key1)
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(encrypted, key2)


def test_decrypt_with_garbage_raises() -> None:
    key = Fernet.generate_key().decode()
    with pytest.raises(SecretDecryptionError):
        decrypt_secret("not-a-valid-ciphertext", key)
