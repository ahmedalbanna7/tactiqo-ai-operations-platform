"""Authenticated encryption adapter for provider credentials."""

from cryptography.fernet import Fernet, InvalidToken


class FernetCredentialCipher:
    """Encrypt credentials with a deployment-owned Fernet key."""

    def __init__(self, key: str) -> None:
        """Validate and retain the configured encryption key."""
        self._fernet = Fernet(key.encode("ascii"))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt and authenticate UTF-8 provider material."""
        return self._fernet.encrypt(plaintext.encode()).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt authenticated material and reject tampering."""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode()
        except InvalidToken as error:
            msg = "Stored integration credential failed authentication."
            raise ValueError(msg) from error
