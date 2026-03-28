"""IntentOS Capability Signing (Phase 4.9) — cryptographic signing for supply chain security."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)


# ─── Models ──────────────────────────────────────────────────────────────────


@dataclass
class KeyPair:
    """Ed25519 key pair with fingerprint-based key_id."""

    public_key: bytes
    private_key: bytes
    key_id: str


@dataclass
class Signature:
    """Cryptographic signature for a capability bundle."""

    key_id: str
    algorithm: str
    hash_hex: str
    signature_bytes: bytes
    signed_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "key_id": self.key_id,
                "algorithm": self.algorithm,
                "hash_hex": self.hash_hex,
                "signature_b64": base64.b64encode(self.signature_bytes).decode(),
                "signed_at": self.signed_at,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> Signature:
        data = json.loads(raw)
        return cls(
            key_id=data["key_id"],
            algorithm=data["algorithm"],
            hash_hex=data["hash_hex"],
            signature_bytes=base64.b64decode(data["signature_b64"]),
            signed_at=data["signed_at"],
        )


@dataclass
class VerificationResult:
    """Result of verifying a bundle signature."""

    is_valid: bool
    key_id: str
    signed_at: Optional[str] = None
    reason: str = ""


# ─── TrustStore ──────────────────────────────────────────────────────────────


class TrustStore:
    """Manages a set of trusted public keys."""

    def __init__(self) -> None:
        # key_id -> (public_key_bytes, name)
        self._keys: Dict[str, Tuple[bytes, str]] = {}

    def add_key(self, public_key: bytes, name: str) -> None:
        key_id = SigningManager.get_key_id(public_key)
        self._keys[key_id] = (public_key, name)

    def remove_key(self, key_id: str) -> None:
        self._keys.pop(key_id, None)

    def is_trusted(self, key_id: str) -> bool:
        return key_id in self._keys

    def get_key(self, key_id: str) -> Optional[bytes]:
        entry = self._keys.get(key_id)
        return entry[0] if entry else None

    def list_keys(self) -> List[Dict[str, str]]:
        return [
            {"key_id": kid, "name": name}
            for kid, (_, name) in self._keys.items()
        ]

    def save(self, path: str) -> None:
        data = {
            kid: {"public_key_b64": base64.b64encode(pk).decode(), "name": name}
            for kid, (pk, name) in self._keys.items()
        }
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str) -> None:
        data = json.loads(Path(path).read_text())
        for kid, entry in data.items():
            pk = base64.b64decode(entry["public_key_b64"])
            self._keys[kid] = (pk, entry["name"])


# ─── SigningManager ──────────────────────────────────────────────────────────


class SigningManager:
    """Manages key generation, signing, and verification of capability bundles."""

    def __init__(self) -> None:
        self.trust_store = TrustStore()

    # ── Key Management ────────────────────────────────────────────────────

    def generate_keypair(self) -> KeyPair:
        private = Ed25519PrivateKey.generate()
        public = private.public_key()

        priv_bytes = private.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        pub_bytes = public.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        key_id = self.get_key_id(pub_bytes)

        return KeyPair(public_key=pub_bytes, private_key=priv_bytes, key_id=key_id)

    def save_keys(self, keypair: KeyPair, dir_path: str) -> None:
        d = Path(dir_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "public.pem").write_bytes(keypair.public_key)
        (d / "private.pem").write_bytes(keypair.private_key)

    def load_keys(self, dir_path: str) -> KeyPair:
        d = Path(dir_path)
        pub = (d / "public.pem").read_bytes()
        priv = (d / "private.pem").read_bytes()
        return KeyPair(public_key=pub, private_key=priv, key_id=self.get_key_id(pub))

    @staticmethod
    def get_key_id(public_key: bytes) -> str:
        return hashlib.sha256(public_key).hexdigest()

    # ── Signing ───────────────────────────────────────────────────────────

    def sign_bundle(self, bundle_path: str, private_key: bytes) -> Signature:
        p = Path(bundle_path)
        if not p.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")

        content = p.read_bytes()
        hash_hex = hashlib.sha256(content).hexdigest()

        priv = load_pem_private_key(private_key, password=None)
        sig_bytes = priv.sign(hash_hex.encode())

        pub_bytes = priv.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )

        return Signature(
            key_id=self.get_key_id(pub_bytes),
            algorithm="ed25519",
            hash_hex=hash_hex,
            signature_bytes=sig_bytes,
            signed_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Verification ──────────────────────────────────────────────────────

    def verify_bundle(
        self, bundle_path: str, signature: Signature, public_key: bytes
    ) -> VerificationResult:
        p = Path(bundle_path)
        content = p.read_bytes()
        current_hash = hashlib.sha256(content).hexdigest()

        if current_hash != signature.hash_hex:
            return VerificationResult(
                is_valid=False,
                key_id=signature.key_id,
                signed_at=signature.signed_at,
                reason="Hash mismatch — bundle may be tampered",
            )

        pub = load_pem_public_key(public_key)
        try:
            pub.verify(signature.signature_bytes, signature.hash_hex.encode())
        except InvalidSignature:
            return VerificationResult(
                is_valid=False,
                key_id=signature.key_id,
                signed_at=signature.signed_at,
                reason="Invalid signature — wrong key or corrupted signature",
            )

        return VerificationResult(
            is_valid=True,
            key_id=signature.key_id,
            signed_at=signature.signed_at,
            reason="valid",
        )

    # ── Integration flow ──────────────────────────────────────────────────

    def sign_and_save(self, bundle_path: str, private_key: bytes) -> Signature:
        sig = self.sign_bundle(bundle_path, private_key)
        sig_path = Path(bundle_path + ".sig")
        sig_path.write_text(sig.to_json())
        return sig

    def verify_from_file(self, bundle_path: str) -> VerificationResult:
        sig_path = Path(bundle_path + ".sig")
        if not sig_path.exists():
            return VerificationResult(
                is_valid=False,
                key_id="",
                reason="Signature file not found",
            )

        sig = Signature.from_json(sig_path.read_text())

        if not self.trust_store.is_trusted(sig.key_id):
            return VerificationResult(
                is_valid=False,
                key_id=sig.key_id,
                signed_at=sig.signed_at,
                reason="Key not in trust store",
            )

        public_key = self.trust_store.get_key(sig.key_id)
        return self.verify_bundle(bundle_path, sig, public_key)
