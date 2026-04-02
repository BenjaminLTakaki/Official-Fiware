#!/usr/bin/env python3
"""
did_helper.py — Derive a did:key from a PKCS12 keystore (EC P-256 key).

Usage:
    python3 did_helper.py <path-to-keystore.p12> <password>

Output:
    Prints the full did:key string to stdout.

Algorithm:
    1. Load the PKCS12 and extract the EC public key.
    2. Get the compressed point (33 bytes for P-256).
    3. Prepend the P-256 multicodec varint prefix: 0x80 0x24.
    4. Base58btc-encode the result.
    5. Prefix with 'z' (multibase indicator for base58btc).
    6. Prepend 'did:key:'.
"""
import sys
from cryptography.hazmat.primitives.serialization.pkcs12 import load_pkcs12
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def b58encode(data: bytes) -> str:
    """Base58 (Bitcoin alphabet) encode bytes."""
    ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(data, "big")
    result = b""
    while n > 0:
        n, r = divmod(n, 58)
        result = bytes([ALPHABET[r]]) + result
    # Preserve leading zero bytes
    for byte in data:
        if byte == 0:
            result = bytes([ALPHABET[0]]) + result
        else:
            break
    return result.decode("ascii")


def encode_varint(value: int) -> bytes:
    """Encode integer as unsigned LEB128 (varint)."""
    result = b""
    while True:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            byte |= 0x80
        result += bytes([byte])
        if value == 0:
            break
    return result


def derive_did_key(p12_path: str, password: str) -> str:
    """Load PKCS12 and derive the did:key."""
    with open(p12_path, "rb") as f:
        p12_data = f.read()

    p12 = load_pkcs12(p12_data, password.encode("utf-8"))
    pub_key = p12.cert.certificate.public_key()

    # Compressed EC point: 33 bytes for P-256
    compressed = pub_key.public_bytes(Encoding.X962, PublicFormat.CompressedPoint)

    # P-256 multicodec code = 0x1200; varint = [0x80, 0x24]
    prefix = encode_varint(0x1200)

    key_bytes = prefix + compressed
    return "did:key:z" + b58encode(key_bytes)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} <keystore.p12> <password>", file=sys.stderr)
        sys.exit(1)

    did = derive_did_key(sys.argv[1], sys.argv[2])
    print(did)
