"""Pre-commit hook: block PII patterns in src/data/*.json files."""

import json
import re
import sys
from pathlib import Path

REAL_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
ALLOWED_EMAILS = {"test@test.com"}
PHONE_RE = re.compile(r"\+[0-9]{10,15}")
UK_POSTCODE_RE = re.compile(r"[A-Z]{1,2}[0-9][0-9A-Z]?\s[0-9][A-Z]{2}")
# First octet 1-255 (our anonymised IP starts with "000." which won't match)
REAL_IP_RE = re.compile(r"\b[1-9][0-9]{0,2}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b")

PATTERN_CHECKS = [
    (REAL_UUID_RE, "real UUID", lambda m: True),
    (EMAIL_RE, "real email", lambda m: m.group().lower() not in ALLOWED_EMAILS),
    (PHONE_RE, "phone number", lambda m: True),
    (UK_POSTCODE_RE, "UK postcode", lambda m: True),
    (REAL_IP_RE, "real IP address", lambda m: True),
]

errors = []

for filepath in sys.argv[1:]:
    path = Path(filepath)
    if path.suffix != ".json":
        continue

    text = path.read_text(encoding="utf-8")

    # Structure check: file-mode fixture must have {"original": ..., "parsed": {...}}
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{filepath}: invalid JSON — {exc}")
        continue

    if "original" not in doc or "parsed" not in doc:
        errors.append(
            f"{filepath}: missing wrapper — file must have top-level "
            f'"original" and "parsed" keys (got: {list(doc.keys())})'
        )
    elif not isinstance(doc["parsed"], dict):
        errors.append(
            f'{filepath}: "parsed" must be a dict, got {type(doc["parsed"]).__name__}'
        )

    # PII pattern checks (run on raw text for speed)
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, label, should_flag in PATTERN_CHECKS:
            for match in pattern.finditer(line):
                if should_flag(match):
                    errors.append(f"{filepath}:{lineno}: {label}: {match.group()!r}")

if errors:
    print("Data file check FAILED:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print(f"Data file check passed ({len(sys.argv) - 1} file(s) checked)")
sys.exit(0)
