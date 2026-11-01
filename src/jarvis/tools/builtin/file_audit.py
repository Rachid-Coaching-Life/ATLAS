"""Read-only duplicate detection inside one user folder.

Nothing here moves, renames, writes or deletes a file. The scan is bounded in
files and time, never follows links, and compares content (size, then a
partial hash, then a full SHA-256) rather than names.
"""
from __future__ import annotations

import hashlib
import os
import stat
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MAX_FILES = 5000
MAX_SECONDS = 8.0
MIN_BYTES = 1024
MAX_HASHED_BYTES = 200 * 1024 * 1024
PARTIAL_BYTES = 64 * 1024
TOP_GROUPS = 5
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class DuplicateGroup:
    size: int
    paths: Tuple[str, ...]  # relative to the scanned folder


@dataclass(frozen=True)
class DuplicateReport:
    groups: Tuple[DuplicateGroup, ...]
    scanned: int
    partial_reason: str
    reclaimable_bytes: int


def _is_link(info: os.stat_result) -> bool:
    return bool(
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _digest(path: str, limit: Optional[int] = None) -> str:
    sha = hashlib.sha256()
    remaining = limit
    with open(path, "rb") as handle:
        while True:
            size = _CHUNK if remaining is None else min(_CHUNK, remaining)
            if size <= 0:
                break
            block = handle.read(size)
            if not block:
                break
            sha.update(block)
            if remaining is not None:
                remaining -= len(block)
    return sha.hexdigest()


def find_duplicates(
    root: Path,
    *,
    max_files: int = MAX_FILES,
    max_seconds: float = MAX_SECONDS,
    min_bytes: int = MIN_BYTES,
    now: Callable[[], float] = time.monotonic,
) -> DuplicateReport:
    """Group byte-identical files below ``root``; read-only and bounded."""
    base = Path(root).resolve(strict=True)
    deadline = now() + max_seconds
    by_size: Dict[int, List[str]] = defaultdict(list)
    scanned = 0
    reason = ""
    pending = [str(base)]
    while pending and not reason:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if now() >= deadline:
                        reason = "limite de durée atteinte"
                        break
                    if scanned >= max_files:
                        reason = "limite de fichiers atteinte"
                        break
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if _is_link(info):
                        continue
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(entry.path)
                    elif stat.S_ISREG(info.st_mode):
                        scanned += 1
                        if info.st_size >= min_bytes:
                            by_size[info.st_size].append(entry.path)
        except OSError:
            continue

    groups: List[DuplicateGroup] = []
    for size, paths in sorted(by_size.items(), key=lambda item: -item[0]):
        if len(paths) < 2 or size > MAX_HASHED_BYTES:
            continue
        if now() >= deadline:
            reason = reason or "limite de durée atteinte"
            break
        partial: Dict[str, List[str]] = defaultdict(list)
        for path in paths:
            try:
                partial[_digest(path, PARTIAL_BYTES)].append(path)
            except OSError:
                continue
        for same_start in partial.values():
            if len(same_start) < 2:
                continue
            full: Dict[str, List[str]] = defaultdict(list)
            for path in same_start:
                try:
                    full[_digest(path)].append(path)
                except OSError:
                    continue
            for identical in full.values():
                if len(identical) > 1:
                    relative = tuple(sorted(os.path.relpath(p, base) for p in identical))
                    groups.append(DuplicateGroup(size, relative))
    groups.sort(key=lambda g: (-(g.size * (len(g.paths) - 1)), g.paths))
    reclaim = sum(g.size * (len(g.paths) - 1) for g in groups)
    return DuplicateReport(tuple(groups), scanned, reason, reclaim)


def _human(size: int) -> str:
    value = float(size)
    for unit in ("octets", "Ko", "Mo", "Go"):
        if value < 1024 or unit == "Go":
            text = f"{value:.0f}" if unit == "octets" else f"{value:.1f}".replace(".", ",")
            return f"{text} {unit}"
        value /= 1024
    return f"{size} octets"


def format_report(folder_label: str, report: DuplicateReport) -> str:
    lines = [
        f"Recherche de doublons dans {folder_label} (lecture seule, "
        f"{report.scanned} fichiers examinés)."
    ]
    if not report.groups:
        lines.append("Aucun doublon trouvé dans le périmètre examiné.")
    else:
        lines.append(
            f"{len(report.groups)} groupe(s) de fichiers identiques ; "
            f"espace récupérable estimé : {_human(report.reclaimable_bytes)}."
        )
        for group in report.groups[:TOP_GROUPS]:
            shown = " | ".join(group.paths[:3])
            extra = f" (+{len(group.paths) - 3})" if len(group.paths) > 3 else ""
            lines.append(f"- {len(group.paths)} x {_human(group.size)} : {shown}{extra}")
        if len(report.groups) > TOP_GROUPS:
            lines.append(f"... et {len(report.groups) - TOP_GROUPS} autre(s) groupe(s).")
    if report.partial_reason:
        lines.append(f"Recherche partielle : {report.partial_reason}.")
    lines.append("Aucun fichier n'a été modifié, déplacé ni supprimé.")
    return "\n".join(lines)
