"""Tests for IntentOS Capability Signing (Phase 4.9)."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from core.platform.signing import (
    KeyPair,
    Signature,
    SigningManager,
    TrustStore,
    VerificationResult,
)


@pytest.fixture
def manager():
    return SigningManager()


@pytest.fixture
def keypair(manager):
    return manager.generate_keypair()


@pytest.fixture
def bundle_file(tmp_path):
    p = tmp_path / "capability.tar.gz"
    p.write_bytes(b"fake-bundle-content-for-testing")
    return p


@pytest.fixture
def trust_store():
    return TrustStore()


# ─── KeyPair model ────────────────────────────────────────────────────────────

class TestKeyPairModel:

    def test_keypair_has_public_key_bytes(self, keypair):
        assert isinstance(keypair.public_key, bytes)
        assert len(keypair.public_key) > 0

    def test_keypair_has_private_key_bytes(self, keypair):
        assert isinstance(keypair.private_key, bytes)
        assert len(keypair.private_key) > 0

    def test_keypair_has_key_id_string(self, keypair):
        assert isinstance(keypair.key_id, str)
        # SHA256 hex digest is 64 chars
        assert len(keypair.key_id) == 64

    def test_key_id_is_sha256_of_public_key(self, manager, keypair):
        expected = manager.get_key_id(keypair.public_key)
        assert keypair.key_id == expected


# ─── Key Management ───────────────────────────────────────────────────────────

class TestKeyManagement:

    def test_generate_keypair_returns_keypair(self, manager):
        kp = manager.generate_keypair()
        assert isinstance(kp, KeyPair)

    def test_generate_unique_keypairs(self, manager):
        kp1 = manager.generate_keypair()
        kp2 = manager.generate_keypair()
        assert kp1.public_key != kp2.public_key

    def test_save_and_load_keys(self, manager, keypair, tmp_path):
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        manager.save_keys(keypair, str(key_dir))
        loaded = manager.load_keys(str(key_dir))
        assert loaded.public_key == keypair.public_key
        assert loaded.private_key == keypair.private_key
        assert loaded.key_id == keypair.key_id

    def test_save_creates_files(self, manager, keypair, tmp_path):
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        manager.save_keys(keypair, str(key_dir))
        assert (key_dir / "public.pem").exists()
        assert (key_dir / "private.pem").exists()

    def test_get_key_id_deterministic(self, manager, keypair):
        id1 = manager.get_key_id(keypair.public_key)
        id2 = manager.get_key_id(keypair.public_key)
        assert id1 == id2


# ─── Signing ──────────────────────────────────────────────────────────────────

class TestSigning:

    def test_sign_bundle_returns_signature(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        assert isinstance(sig, Signature)

    def test_signature_fields(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        assert sig.key_id == keypair.key_id
        assert sig.algorithm == "ed25519"
        assert isinstance(sig.hash_hex, str) and len(sig.hash_hex) == 64
        assert isinstance(sig.signature_bytes, bytes)
        assert sig.signed_at is not None

    def test_sign_nonexistent_file_raises(self, manager, keypair):
        with pytest.raises(FileNotFoundError):
            manager.sign_bundle("/nonexistent/path.tar.gz", keypair.private_key)


# ─── Verification ─────────────────────────────────────────────────────────────

class TestVerification:

    def test_verify_valid_bundle(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        result = manager.verify_bundle(str(bundle_file), sig, keypair.public_key)
        assert isinstance(result, VerificationResult)
        assert result.is_valid is True
        assert result.key_id == keypair.key_id
        assert result.reason == "valid"

    def test_verify_tampered_bundle(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        bundle_file.write_bytes(b"tampered-content")
        result = manager.verify_bundle(str(bundle_file), sig, keypair.public_key)
        assert result.is_valid is False
        assert "tamper" in result.reason.lower() or "hash" in result.reason.lower()

    def test_verify_wrong_key(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        other = manager.generate_keypair()
        result = manager.verify_bundle(str(bundle_file), sig, other.public_key)
        assert result.is_valid is False


# ─── Signature serialization ─────────────────────────────────────────────────

class TestSignatureSerialization:

    def test_to_json_and_from_json_roundtrip(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        json_str = sig.to_json()
        restored = Signature.from_json(json_str)
        assert restored.key_id == sig.key_id
        assert restored.algorithm == sig.algorithm
        assert restored.hash_hex == sig.hash_hex
        assert restored.signature_bytes == sig.signature_bytes
        assert restored.signed_at == sig.signed_at

    def test_to_json_is_valid_json(self, manager, keypair, bundle_file):
        sig = manager.sign_bundle(str(bundle_file), keypair.private_key)
        data = json.loads(sig.to_json())
        assert "key_id" in data
        assert "algorithm" in data


# ─── TrustStore ──────────────────────────────────────────────────────────────

class TestTrustStore:

    def test_add_and_is_trusted(self, trust_store, keypair):
        trust_store.add_key(keypair.public_key, "test-key")
        assert trust_store.is_trusted(keypair.key_id) is True

    def test_remove_key(self, trust_store, keypair):
        trust_store.add_key(keypair.public_key, "test-key")
        trust_store.remove_key(keypair.key_id)
        assert trust_store.is_trusted(keypair.key_id) is False

    def test_get_key(self, trust_store, keypair):
        trust_store.add_key(keypair.public_key, "test-key")
        retrieved = trust_store.get_key(keypair.key_id)
        assert retrieved == keypair.public_key

    def test_list_keys(self, trust_store, manager):
        kp1 = manager.generate_keypair()
        kp2 = manager.generate_keypair()
        trust_store.add_key(kp1.public_key, "key-1")
        trust_store.add_key(kp2.public_key, "key-2")
        keys = trust_store.list_keys()
        assert len(keys) == 2

    def test_save_and_load(self, trust_store, keypair, tmp_path):
        trust_store.add_key(keypair.public_key, "test-key")
        path = str(tmp_path / "trust.json")
        trust_store.save(path)
        loaded = TrustStore()
        loaded.load(path)
        assert loaded.is_trusted(keypair.key_id)
        assert loaded.get_key(keypair.key_id) == keypair.public_key

    def test_empty_trust_store(self, trust_store):
        assert trust_store.is_trusted("anything") is False
        assert trust_store.list_keys() == []


# ─── Integration flow ────────────────────────────────────────────────────────

class TestIntegrationFlow:

    def test_sign_and_save_creates_sig_file(self, manager, keypair, bundle_file):
        manager.sign_and_save(str(bundle_file), keypair.private_key)
        sig_path = Path(str(bundle_file) + ".sig")
        assert sig_path.exists()

    def test_verify_from_file_valid(self, manager, keypair, bundle_file):
        trust_store = TrustStore()
        trust_store.add_key(keypair.public_key, "author")
        manager.trust_store = trust_store
        manager.sign_and_save(str(bundle_file), keypair.private_key)
        result = manager.verify_from_file(str(bundle_file))
        assert result.is_valid is True

    def test_verify_from_file_no_sig(self, manager, bundle_file):
        result = manager.verify_from_file(str(bundle_file))
        assert result.is_valid is False
        assert "signature file" in result.reason.lower() or "not found" in result.reason.lower()
