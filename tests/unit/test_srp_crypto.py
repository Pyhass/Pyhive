"""Unit tests for pure SRP/HKDF crypto helpers — no mocking needed."""

from apyhiveapi.api.srp_crypto import (
    calculate_u,
    compute_hkdf,
    hash_sha256,
    hex_hash,
    hex_to_long,
    long_to_hex,
    pad_hex,
)

# Constants for magic numbers
HEX_FF = 255
HEX_100 = 256
SHA256_HEX_LEN = 64
HKDF_OUTPUT_LEN = 16


def test_hex_to_long_ff():
    """Test hex_to_long converts 'ff' to 255."""
    assert hex_to_long("ff") == HEX_FF


def test_hex_to_long_zero():
    """Test hex_to_long converts '0' to 0."""
    assert hex_to_long("0") == 0


def test_hex_to_long_large():
    """Test hex_to_long converts '100' to 256."""
    assert hex_to_long("100") == HEX_100


def test_hash_sha256_returns_64_char_hex():
    """Test hash_sha256 returns 64-character hex string."""
    result = hash_sha256(b"hello")
    assert len(result) == SHA256_HEX_LEN
    assert all(c in "0123456789abcdef" for c in result)


def test_hash_sha256_zero_padded():
    """Test hash_sha256 returns zero-padded 64-char output."""
    # Must always be 64 chars even if leading zeros needed
    result = hash_sha256(b"")
    assert len(result) == SHA256_HEX_LEN


def test_hex_hash_consistent_with_hash_sha256():
    """Test hex_hash produces same result as hash_sha256 on hex input."""
    hex_input = "ff"
    assert hex_hash(hex_input) == hash_sha256(bytearray.fromhex(hex_input))


def test_long_to_hex():
    """Test long_to_hex converts integers to hex strings."""
    assert long_to_hex(HEX_FF) == "ff"
    assert long_to_hex(0) == "0"


def test_pad_hex_odd_length_gets_leading_zero():
    """Test pad_hex adds leading zero for odd-length strings."""
    # long_to_hex(1) = "1" (odd) → "01"
    assert pad_hex(1) == "01"


def test_pad_hex_high_nibble_gets_00_prefix():
    """Test pad_hex adds 00 prefix for high-nibble values."""
    # long_to_hex(255) = "ff", 'f' is in high-nibble set → "00ff"
    assert pad_hex(HEX_FF) == "00ff"


def test_pad_hex_normal_even_low_nibble_unchanged():
    """Test pad_hex leaves even-length low-nibble values unchanged."""
    # 0x1a = "1a", even length, '1' not in high-nibble set → "1a"
    assert pad_hex(0x1A) == "1a"


def test_pad_hex_string_input_odd():
    """Test pad_hex handles string input with odd length."""
    assert pad_hex("abc") == "0abc"


def test_calculate_u_returns_int():
    """Test calculate_u returns a positive integer."""
    result = calculate_u(12345, 67890)
    assert isinstance(result, int)
    assert result > 0


def test_compute_hkdf_returns_16_bytes():
    """Test compute_hkdf returns 16-byte output."""
    ikm = b"input_key_material"
    salt = b"salt_value_here!"
    result = compute_hkdf(ikm, salt)
    assert isinstance(result, bytes)
    assert len(result) == HKDF_OUTPUT_LEN


def test_compute_hkdf_deterministic():
    """Test compute_hkdf produces deterministic output."""
    ikm = b"test"
    salt = b"salt"
    assert compute_hkdf(ikm, salt) == compute_hkdf(ikm, salt)


def test_compute_hkdf_different_inputs_produce_different_outputs():
    """Different ikm inputs produce different HKDF outputs."""
    salt = b"same_salt"
    result1 = compute_hkdf(b"input_one", salt)
    result2 = compute_hkdf(b"input_two", salt)
    assert result1 != result2


def test_long_to_hex_and_back_is_identity():
    """hex_to_long(long_to_hex(n)) == n for positive integers."""
    for value in [1, 255, 256, 65535, 2**32]:
        assert hex_to_long(long_to_hex(value)) == value


def test_pad_hex_high_nibble_string_input():
    """pad_hex with string "ff" (high nibble) gets "00" prefix."""
    assert pad_hex("ff") == "00ff"


def test_hash_sha256_deterministic():
    """hash_sha256 returns the same output for the same input."""
    assert hash_sha256(b"test") == hash_sha256(b"test")


def test_calculate_u_with_large_srp_values():
    """calculate_u handles large SRP-scale integers."""
    large_a = 2**256
    large_b = 2**256 + 1
    result = calculate_u(large_a, large_b)
    assert isinstance(result, int)
    assert result > 0
