import hashlib

from osm_scientific_converter.core.hashing import sha256_file


def test_sha256_file(tmp_path):
    path = tmp_path / "样本.bin"
    path.write_bytes(b"abc\x00def")
    assert sha256_file(path) == hashlib.sha256(b"abc\x00def").hexdigest()

