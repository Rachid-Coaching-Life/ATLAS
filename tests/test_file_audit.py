"""Duplicate detection is read-only, content-based and bounded."""
import os
from pathlib import Path

import pytest

from jarvis.tools.builtin import file_audit as fa

pytestmark = pytest.mark.unit

BIG = b"A" * 2048


def make(root: Path, name: str, data: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_identical_files_are_grouped_even_with_different_names(tmp_path):
    make(tmp_path, "cours.bin", BIG)
    make(tmp_path, "copie de cours.bin", BIG)
    make(tmp_path, "sub/archive.bin", BIG)
    make(tmp_path, "unique.bin", b"B" * 2048)
    report = fa.find_duplicates(tmp_path)
    assert len(report.groups) == 1
    assert len(report.groups[0].paths) == 3
    assert report.reclaimable_bytes == 2 * 2048
    assert report.scanned == 4


def test_same_size_different_content_is_not_a_duplicate(tmp_path):
    make(tmp_path, "a.bin", b"A" * 2048)
    make(tmp_path, "b.bin", b"A" * 2047 + b"B")
    assert fa.find_duplicates(tmp_path).groups == ()


def test_small_files_are_ignored(tmp_path):
    make(tmp_path, "a.txt", b"x" * 100)
    make(tmp_path, "b.txt", b"x" * 100)
    assert fa.find_duplicates(tmp_path).groups == ()


def test_difference_after_the_partial_hash_is_detected(tmp_path):
    head = b"H" * fa.PARTIAL_BYTES
    make(tmp_path, "a.bin", head + b"one")
    make(tmp_path, "b.bin", head + b"two")
    make(tmp_path, "c.bin", head + b"one")
    report = fa.find_duplicates(tmp_path)
    assert len(report.groups) == 1
    assert sorted(report.groups[0].paths) == ["a.bin", "c.bin"]


def test_scan_never_modifies_files(tmp_path):
    first = make(tmp_path, "a.bin", BIG)
    second = make(tmp_path, "b.bin", BIG)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (first, second)}
    fa.find_duplicates(tmp_path)
    assert sorted(os.listdir(tmp_path)) == ["a.bin", "b.bin"]
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (first, second)} == before


def test_symbolic_links_are_not_followed(tmp_path):
    real = make(tmp_path, "real.bin", BIG)
    try:
        (tmp_path / "link.bin").symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not allowed on this system")
    assert fa.find_duplicates(tmp_path).groups == ()


def test_file_limit_reports_a_partial_scan(tmp_path):
    for index in range(6):
        make(tmp_path, f"f{index}.bin", bytes([index]) * 2048)
    report = fa.find_duplicates(tmp_path, max_files=3)
    assert report.scanned == 3 and "fichiers" in report.partial_reason


def test_time_limit_reports_a_partial_scan(tmp_path):
    make(tmp_path, "a.bin", BIG)
    clock = iter([0.0] + [100.0] * 50)
    report = fa.find_duplicates(tmp_path, max_seconds=1.0, now=lambda: next(clock))
    assert "durée" in report.partial_reason


def test_report_is_explicit_about_read_only_and_limits(tmp_path):
    make(tmp_path, "a.bin", BIG)
    make(tmp_path, "b.bin", BIG)
    text = fa.format_report("Documents", fa.find_duplicates(tmp_path))
    assert "lecture seule" in text and "1 groupe" in text
    assert "a.bin" in text and "b.bin" in text
    assert "Aucun fichier n'a été modifié, déplacé ni supprimé." in text


def test_empty_report_says_so(tmp_path):
    text = fa.format_report("Documents", fa.find_duplicates(tmp_path))
    assert "Aucun doublon" in text


def test_many_groups_are_summarised(tmp_path):
    for index in range(8):
        data = bytes([index + 1]) * 2048
        make(tmp_path, f"x{index}.bin", data)
        make(tmp_path, f"y{index}.bin", data)
    text = fa.format_report("Documents", fa.find_duplicates(tmp_path))
    assert "8 groupe" in text and "3 autre(s) groupe(s)" in text


@pytest.mark.parametrize("size,expected", [(10, "10 octets"), (2048, "2,0 Ko"), (5 * 1024 * 1024, "5,0 Mo")])
def test_human_sizes(size, expected):
    assert fa._human(size) == expected
