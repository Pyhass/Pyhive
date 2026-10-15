"""Pure SRP/HKDF crypto helpers for AWS Cognito authentication."""

import binascii
import hashlib
import hmac
import os

# https://github.com/aws/amazon-cognito-identity-js/blob/master/src/AuthenticationHelper.js#L22
N_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    + "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    + "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    + "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    + "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    + "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    + "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    + "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    + "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    + "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    + "15728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64"
    + "ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    + "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6B"
    + "F12FFA06D98A0864D87602733EC86A64521F2B18177B200C"
    + "BBE117577A615D6C770988C0BAD946E208E24FA074E5AB31"
    + "43DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"
)
# https://github.com/aws/amazon-cognito-identity-js/blob/master/src/AuthenticationHelper.js#L49
G_HEX = "2"
INFO_BITS = bytearray("Caldera Derived Key", "utf-8")


def hex_to_long(hex_string):
    """Convert hex to long number."""
    return int(hex_string, 16)


def get_random(nbytes):
    """Generate a random hex number."""
    random_hex = binascii.hexlify(os.urandom(nbytes))
    return hex_to_long(random_hex)


def hash_sha256(buf):
    """Authentication helper."""
    a_value = hashlib.sha256(buf).hexdigest()
    return (64 - len(a_value)) * "0" + a_value


def hex_hash(hex_string):
    """Convert hex value to hash."""
    return hash_sha256(bytearray.fromhex(hex_string))


def calculate_u(big_a, big_b):
    """
    Calculate the client's value U which is the hash of A and B.

    :param {Long integer} big_a Large A value.
    :param {Long integer} big_b Server B value.
    :return {Long integer} Computed U value.
    """
    u_hex_hash = hex_hash(pad_hex(big_a) + pad_hex(big_b))
    return hex_to_long(u_hex_hash)


def long_to_hex(long_num):
    """Convert long number to hex."""
    return f"{long_num:x}"


def pad_hex(long_int):
    """Convert integer to hex format."""
    if not isinstance(long_int, str):
        hash_str = long_to_hex(long_int)
    else:
        hash_str = long_int
    if len(hash_str) % 2 == 1:
        hash_str = f"0{hash_str}"
    elif hash_str[0] in "89ABCDEFabcdef":
        hash_str = f"00{hash_str}"
    return hash_str


def compute_hkdf(ikm, salt):
    """Process the hkdf algorithm."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    info_bits_update = INFO_BITS + bytearray(chr(1), "utf-8")
    hmac_hash = hmac.new(prk, info_bits_update, hashlib.sha256).digest()
    return hmac_hash[:16]
