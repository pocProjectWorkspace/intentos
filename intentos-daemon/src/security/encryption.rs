use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    Aes256Gcm, Nonce,
};
use hkdf::Hkdf;
use rand::RngCore;
use sha2::Sha256;
use serde::{Deserialize, Serialize};

const SALT_SIZE: usize = 32;
const NONCE_SIZE: usize = 12;
const KEY_SIZE: usize = 32;

/// Encrypted data container
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedBlob {
    pub salt: Vec<u8>,
    pub nonce: Vec<u8>,
    pub ciphertext: Vec<u8>,
}

/// AES-256-GCM credential store
pub struct CredentialStore {
    master_key: Vec<u8>,
}

impl CredentialStore {
    pub fn new(master_key: Vec<u8>) -> Result<Self, String> {
        if master_key.len() < KEY_SIZE {
            return Err(format!(
                "Master key must be at least {} bytes, got {}",
                KEY_SIZE,
                master_key.len()
            ));
        }
        Ok(Self { master_key })
    }

    /// Derive a per-secret key from master key + salt
    fn derive_key(&self, salt: &[u8]) -> Vec<u8> {
        let hk = Hkdf::<Sha256>::new(Some(salt), &self.master_key);
        let mut key = vec![0u8; KEY_SIZE];
        hk.expand(b"intentos-credential-encryption-v1", &mut key)
            .expect("HKDF expand failed");
        key
    }

    /// Encrypt plaintext with unique salt and nonce
    pub fn encrypt(&self, plaintext: &str) -> Result<EncryptedBlob, String> {
        let mut salt = vec![0u8; SALT_SIZE];
        OsRng.fill_bytes(&mut salt);

        let mut nonce_bytes = vec![0u8; NONCE_SIZE];
        OsRng.fill_bytes(&mut nonce_bytes);

        let derived_key = self.derive_key(&salt);
        let cipher = Aes256Gcm::new_from_slice(&derived_key)
            .map_err(|e| format!("Cipher init failed: {}", e))?;

        let nonce = Nonce::from_slice(&nonce_bytes);
        let ciphertext = cipher
            .encrypt(nonce, plaintext.as_bytes())
            .map_err(|e| format!("Encryption failed: {}", e))?;

        Ok(EncryptedBlob {
            salt,
            nonce: nonce_bytes,
            ciphertext,
        })
    }

    /// Decrypt an EncryptedBlob back to plaintext
    pub fn decrypt(&self, blob: &EncryptedBlob) -> Result<String, String> {
        let derived_key = self.derive_key(&blob.salt);
        let cipher = Aes256Gcm::new_from_slice(&derived_key)
            .map_err(|e| format!("Cipher init failed: {}", e))?;

        let nonce = Nonce::from_slice(&blob.nonce);
        let plaintext_bytes = cipher
            .decrypt(nonce, blob.ciphertext.as_ref())
            .map_err(|_| "Decryption failed — wrong key or tampered data".to_string())?;

        String::from_utf8(plaintext_bytes)
            .map_err(|e| format!("UTF-8 decode failed: {}", e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_key() -> Vec<u8> {
        let mut key = vec![0u8; 32];
        OsRng.fill_bytes(&mut key);
        key
    }

    #[test]
    fn test_roundtrip() {
        let store = CredentialStore::new(test_key()).unwrap();
        let blob = store.encrypt("sk-ant-secret-key").unwrap();
        let result = store.decrypt(&blob).unwrap();
        assert_eq!(result, "sk-ant-secret-key");
    }

    #[test]
    fn test_unique_ciphertexts() {
        let store = CredentialStore::new(test_key()).unwrap();
        let blob1 = store.encrypt("same").unwrap();
        let blob2 = store.encrypt("same").unwrap();
        assert_ne!(blob1.ciphertext, blob2.ciphertext);
    }

    #[test]
    fn test_wrong_key_fails() {
        let store1 = CredentialStore::new(test_key()).unwrap();
        let store2 = CredentialStore::new(test_key()).unwrap();
        let blob = store1.encrypt("secret").unwrap();
        assert!(store2.decrypt(&blob).is_err());
    }

    #[test]
    fn test_tampered_ciphertext_fails() {
        let store = CredentialStore::new(test_key()).unwrap();
        let mut blob = store.encrypt("secret").unwrap();
        if !blob.ciphertext.is_empty() {
            blob.ciphertext[0] ^= 0xFF;
        }
        assert!(store.decrypt(&blob).is_err());
    }

    #[test]
    fn test_short_key_rejected() {
        assert!(CredentialStore::new(vec![0u8; 16]).is_err());
    }

    #[test]
    fn test_empty_plaintext() {
        let store = CredentialStore::new(test_key()).unwrap();
        let blob = store.encrypt("").unwrap();
        let result = store.decrypt(&blob).unwrap();
        assert_eq!(result, "");
    }

    #[test]
    fn test_unicode() {
        let store = CredentialStore::new(test_key()).unwrap();
        let blob = store.encrypt("パスワード-密码").unwrap();
        let result = store.decrypt(&blob).unwrap();
        assert_eq!(result, "パスワード-密码");
    }
}
