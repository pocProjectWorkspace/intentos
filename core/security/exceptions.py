"""
Security-specific exceptions for IntentOS.

All exceptions inherit from SecurityError for catch-all handling.
Error messages are plain language — never expose internals to users.
"""


class SecurityError(Exception):
    """Base exception for all security operations."""

    pass


class EncryptionError(SecurityError):
    """Raised when encryption fails."""

    pass


class DecryptionError(SecurityError):
    """Raised when decryption fails — wrong key, corrupted data, or tampered ciphertext."""

    pass


class TamperedDataError(DecryptionError):
    """Raised when authentication tag verification fails — data has been modified."""

    pass


class MasterKeyError(SecurityError):
    """Raised when the master key is invalid, missing, or too short."""

    pass


class KeychainError(SecurityError):
    """Raised when OS keychain operations fail."""

    pass


class LeakDetectedError(SecurityError):
    """Raised when a credential leak is detected in output."""

    def __init__(self, message: str, pattern_name: str, severity: str):
        super().__init__(message)
        self.pattern_name = pattern_name
        self.severity = severity
