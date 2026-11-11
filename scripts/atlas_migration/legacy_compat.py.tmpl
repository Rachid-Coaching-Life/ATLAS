"""Compatibility with the former product name: environment, settings and user data.

Three things, none of them destructive:

* ``JARVIS_*`` environment variables are accepted as aliases of ``ATLAS_*``;
  an ``ATLAS_*`` variable that is already set always wins;
* the former per-user configuration and data directories are copied once to
  their new names (the originals are never moved, modified or deleted);
* keys of a copied ``config.json`` that carry the former name are renamed.

Set ``ATLAS_SKIP_LEGACY_MIGRATION=1`` to disable the copy. It is skipped
automatically under pytest. This module must not import other atlas modules.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_LOG = logging.getLogger("atlas.legacy")
_OLD_PREFIX = "JARVIS_"
_NEW_PREFIX = "ATLAS_"
MARKER = ".migrated-from-legacy.json"
SKIP_VARIABLE = "ATLAS_SKIP_LEGACY_MIGRATION"


def _new_text(name: str) -> str:
    """Name of a directory or file: Jarvis -> ATLAS, jarvis -> atlas."""
    return name.replace("JARVIS", "ATLAS").replace("Jarvis", "ATLAS").replace("jarvis", "atlas")


def _new_key(name: str) -> str:
    """Key of a settings file: identifier style."""
    return name.replace("JARVIS", "ATLAS").replace("Jarvis", "Atlas").replace("jarvis", "atlas")


def apply_env_aliases(environ: Optional[Dict[str, str]] = None) -> List[str]:
    """Copy JARVIS_X to ATLAS_X when ATLAS_X is not set. Returns the new names."""
    env = os.environ if environ is None else environ
    created = []
    for key in list(env):
        if key.startswith(_OLD_PREFIX):
            new = _NEW_PREFIX + key[len(_OLD_PREFIX):]
            if new not in env:
                env[new] = env[key]
                created.append(new)
    if created:
        _LOG.warning("Former environment variables are deprecated, use: %s", ", ".join(sorted(created)))
    return created


def legacy_locations(home=None, environ=None, platform: Optional[str] = None) -> List[Tuple[Path, Path]]:
    """(former directory, new directory) pairs that exist on this machine."""
    env = os.environ if environ is None else environ
    base_home = Path(home) if home else Path.home()
    system = platform or sys.platform
    bases = [base_home / ".config", base_home / ".local" / "share"]
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "APPDATA", "LOCALAPPDATA"):
        if env.get(variable):
            bases.append(Path(env[variable]))
    if system == "darwin":
        bases.append(base_home / "Library" / "Application Support")
    candidates = [(base / name, base / _new_text(name)) for base in bases for name in ("jarvis", "Jarvis")]
    candidates.append((base_home / ".jarvis", base_home / ".atlas"))
    pairs, seen = [], set()
    for old, new in candidates:
        if not old.is_dir():
            continue
        identity = os.path.normcase(os.path.realpath(old))
        if identity in seen:
            continue
        seen.add(identity)
        pairs.append((old, new))
    return pairs


def _rename_keys(value):
    if isinstance(value, dict):
        renamed = {}
        for key, item in value.items():
            new = _new_key(key) if isinstance(key, str) else key
            if new != key and new in value:
                new = key  # never overwrite a key the file already has
            renamed[new] = _rename_keys(item)
        return renamed
    if isinstance(value, list):
        return [_rename_keys(item) for item in value]
    return value


def _copy_renamed(old: Path, new: Path) -> None:
    """Copy a tree, renaming files and folders that carry the former name."""
    new.mkdir(parents=True)
    for current, folders, files in os.walk(old):
        relative = Path(current).relative_to(old)
        target = new.joinpath(*[_new_text(part) for part in relative.parts])
        target.mkdir(parents=True, exist_ok=True)
        for folder in folders:
            target.joinpath(_new_text(folder)).mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copy2(Path(current) / name, target / _new_text(name))


def _migrate_one(old: Path, new: Path) -> bool:
    staging = new.with_name(new.name + ".migrating-" + str(os.getpid()))
    if staging.exists():
        shutil.rmtree(staging)
    _copy_renamed(old, staging)
    config = staging / "config.json"
    if config.is_file():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            config.write_text(json.dumps(_rename_keys(data), indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError):
            _LOG.warning("config.json was copied unchanged (not valid JSON)")
    (staging / MARKER).write_text(
        json.dumps({"copied_from": str(old), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
    try:
        os.replace(staging, new)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)  # another process finished first
        return False
    return True


def migrate_user_data(home=None, environ=None, platform: Optional[str] = None, force: bool = False) -> List[Path]:
    """Copy former user directories to their new names once. Never raises."""
    env = os.environ if environ is None else environ
    if not force and (env.get(SKIP_VARIABLE) or "pytest" in sys.modules):
        return []
    created = []
    try:
        pairs = legacy_locations(home, env, platform)
    except OSError:
        return []
    for old, new in pairs:
        if new.exists():
            continue
        try:
            if _migrate_one(old, new):
                created.append(new)
                _LOG.info("User data copied from %s to %s; the original was left untouched", old, new)
        except Exception as error:  # noqa: BLE001 - startup must never fail because of a copy
            _LOG.warning("User data not copied from %s: %s", old, error)
    return created
