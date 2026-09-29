"""src.snapshot: publish, hash list, verify, restore (on a temp tree), and the committed snapshot."""

from __future__ import annotations

from src import config, snapshot


def test_publish_rehash_verify(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    snap = tmp_path / "snapshot"
    processed.mkdir()
    monkeypatch.setattr(config, "PROCESSED_DIR", processed)
    a = processed / "a.json"
    a.write_text("{}")
    snapshot.publish([a], root=snap)
    assert (snap / "a.json").read_text() == "{}"
    sums = (snap / "SHA256SUMS").read_text()
    assert "  a.json" in sums
    assert snapshot.verify(snap) == []

    (snap / "a.json").write_text('{"x": 1}')
    assert snapshot.verify(snap) == ["hash mismatch: a.json"]
    (snap / "b.json").write_text("[]")
    assert "not listed: b.json" in snapshot.verify(snap)


def test_restore_copies_missing_files(tmp_path):
    snap = tmp_path / "snapshot"
    snap.mkdir()
    (snap / "a.json").write_text("{}")
    snapshot.rehash(snap)
    dest = tmp_path / "processed"
    assert snapshot.restore(snap, dest) == 1
    assert (dest / "a.json").exists()
    assert not (dest / "SHA256SUMS").exists()


def test_committed_snapshot_matches_its_hash_list():
    assert snapshot.verify() == []
