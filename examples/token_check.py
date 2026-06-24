"""Second demo file: adds one new issue to test re-review dedup."""

import hashlib


def verify_token(provided, expected):
    # Compare the two token hashes.
    provided_hash = hashlib.md5(provided.encode()).hexdigest()
    expected_hash = hashlib.md5(expected.encode()).hexdigest()
    return provided_hash == expected_hash
