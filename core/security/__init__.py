"""
IntentOS Security Module

Enterprise-grade security primitives for credential management,
leak detection, prompt injection defense, and sandbox enforcement.
"""

from core.security.exceptions import (
    SecurityError,
    EncryptionError,
    DecryptionError,
    KeychainError,
    TamperedDataError,
    MasterKeyError,
)

__all__ = [
    "SecurityError",
    "EncryptionError",
    "DecryptionError",
    "KeychainError",
    "TamperedDataError",
    "MasterKeyError",
]
