# lib/memo/crypto.py
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode((s or "").encode("ascii"))


@dataclass
class EncMeta:
    alg: str = "AES-256-GCM"
    kdf: str = "scrypt"
    salt_b64: str = ""
    nonce_b64: str = ""


def derive_key_scrypt(passphrase: str, salt: bytes) -> bytes:
    """
    passphrase + salt -> 32 bytes key (AES-256)
    """
    if not passphrase:
        raise ValueError("passphrase is empty")
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=2**14,   # 16384
        r=8,
        p=1,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_text(passphrase: str, plaintext: str) -> Tuple[str, dict]:
    """
    returns: (ciphertext_b64, enc_dict)
    """
    salt = os.urandom(16)
    nonce = os.urandom(12)  # AESGCM recommended nonce size
    key = derive_key_scrypt(passphrase, salt)

    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, (plaintext or "").encode("utf-8"), associated_data=None)

    enc = EncMeta(salt_b64=_b64e(salt), nonce_b64=_b64e(nonce))
    enc_dict = {
        "alg": enc.alg,
        "kdf": enc.kdf,
        "salt": enc.salt_b64,
        "nonce": enc.nonce_b64,
    }
    return _b64e(ct), enc_dict


def decrypt_text(passphrase: str, ciphertext_b64: str, enc: dict) -> str:
    """
    raises on failure (wrong key / corrupted)
    """
    if not passphrase:
        raise ValueError("passphrase is empty")
    if not enc:
        raise ValueError("enc metadata missing")

    salt = _b64d(enc.get("salt", ""))
    nonce = _b64d(enc.get("nonce", ""))
    ct = _b64d(ciphertext_b64)

    key = derive_key_scrypt(passphrase, salt)
    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, associated_data=None)
    return pt.decode("utf-8")

# lib/memo/crypto.py に追加
def is_encrypted(raw: dict) -> bool:
    return bool(raw.get("content_enc"))


# ============================================================
# メモ（pages/05_メモ.py）から切り出し：暗号化メモ判定・復号ガード
# ============================================================

def is_encrypted_note(raw: dict) -> bool:
    """暗号化メモ判定：content_enc がある（タグ推測はしない）"""
    return bool((raw or {}).get("content_enc"))


def decrypt_content_if_possible(raw: dict, passphrase: str) -> tuple[bool, str, str]:
    """
    returns: (ok, plaintext, err_msg)
    - 暗号化でないなら content を返す
    - 暗号化なら passphrase が必要
    """
    if not is_encrypted_note(raw):
        return True, (raw.get("content", "") or ""), ""

    if not passphrase:
        return False, "", "🔐 暗号化メモです。左のサイドバーで復号キーを入力してください。"

    try:
        pt = decrypt_text(
            passphrase=passphrase,
            ciphertext_b64=str(raw.get("content_enc", "") or ""),
            enc=raw.get("enc", {}) or {},
        )
        return True, pt, ""
    except Exception:
        return False, "", "🔐 復号に失敗しました（キーが違うか、データが壊れています）。"
