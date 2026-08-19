"""Generation, hashing and authenticated encryption of endpoint secrets."""

import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken


class SecretDecryptionError(ValueError):
    """Raised when an endpoint secret cannot be decrypted."""


def generate_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(32)}"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def encrypt_secret(secret: str, encryption_key: str) -> str:
    return Fernet(encryption_key.encode()).encrypt(secret.encode()).decode()


def decrypt_secret(ciphertext: str, encryption_key: str) -> str:
    try:
        return Fernet(encryption_key.encode()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise SecretDecryptionError("Webhook secret could not be decrypted") from exc
