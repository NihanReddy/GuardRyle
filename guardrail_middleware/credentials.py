from __future__ import annotations


class CredentialStoreError(RuntimeError):
    """Raised when the configured OS credential store cannot be used."""


class CredentialStore:
    """Persist secrets through the host OS credential manager."""

    def __init__(self, service: str = "guardryle", account: str = "openai-api-key"):
        self.service = service
        self.account = account

    def get(self) -> str | None:
        keyring = self._keyring()
        try:
            return keyring.get_password(self.service, self.account)
        except keyring.errors.KeyringError as exc:
            raise CredentialStoreError("Secure credential storage is unavailable.") from exc

    def set(self, secret: str) -> None:
        keyring = self._keyring()
        try:
            keyring.set_password(self.service, self.account, secret)
        except keyring.errors.KeyringError as exc:
            raise CredentialStoreError("Secure credential storage is unavailable.") from exc

    def _keyring(self):
        try:
            import keyring
        except ImportError as exc:
            raise CredentialStoreError("Secure credential storage is unavailable.") from exc
        return keyring
