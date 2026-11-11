"""Path resolution for ``localFiles``, shared by the tool and the confirmation text.

Contract:

* a relative path is relative to the user's home directory, never to the
  current working directory of the process;
* every path must stay inside the home directory;
* ``write``, ``append`` and ``delete`` refuse any path that crosses a symbolic
  link or a Windows junction, so that the target shown to the user is the file
  that is acted on. ``Path.resolve()`` alone is not enough for that: it follows
  links silently, and the answer can change between the check and the use.

This module only depends on the standard library so that the confirmation
gate can import it without a cycle.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

# Windows reparse tags that redirect a path: symbolic link and mount point
# (junction). Other reparse points (cloud placeholders such as OneDrive files)
# do not redirect and are left alone.
_REDIRECTING_REPARSE_TAGS = frozenset({0xA000000C, 0xA0000003})
_READ_OPERATIONS = frozenset({"list", "search", "read"})
_MAX_PATH_CHARS = 4096


def home_root() -> Path:
    return Path(os.path.expanduser("~")).resolve()


def expand_user_path(path: str) -> str:
    """Absolute form of ``path`` (not normalised). Relative means "inside home"."""
    home = os.path.expanduser("~")
    if path == "~":
        return home
    if path.startswith("~/") or path.startswith("~\\"):
        return os.path.join(home, path[2:])
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return expanded
    if os.name == "nt" and (os.path.splitdrive(expanded)[0] or expanded.startswith(("/", "\\"))):
        raise PermissionError("Path not allowed: ambiguous drive-relative path")
    return os.path.join(home, expanded)


def resolve_home_path(path: str) -> Path:
    """Resolved path (links followed) for read-only operations; must be in home."""
    home = home_root()
    resolved = Path(expand_user_path(path)).resolve()
    if resolved == home or str(resolved).startswith(str(home) + os.sep):
        return resolved
    raise PermissionError(f"Path not allowed: {resolved}")


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_reparse_tag", 0) in _REDIRECTING_REPARSE_TAGS
    )


def _home_relative(lexical: str) -> str | None:
    """Part of ``lexical`` below the home directory, or None when outside."""
    for base in dict.fromkeys((os.path.abspath(os.path.expanduser("~")), str(home_root()))):
        root = os.path.normcase(base).rstrip(os.sep)
        folded = os.path.normcase(lexical)
        if folded == root:
            return ""
        if folded.startswith(root + os.sep):
            return lexical[len(root) + 1:]
    return None


def resolve_mutation_target(path: str) -> Path:
    """Link-free target of ``path`` for write, append and delete.

    The path is normalised lexically (``..`` collapsed), must lie inside the
    home directory, and no existing component below home may be a symbolic
    link or a junction. The returned path is built from the resolved home
    directory and that normalised remainder, so it is exactly what is shown
    by :func:`describe_target` and what the tool opens.
    """
    lexical = os.path.abspath(expand_user_path(path))
    relative = _home_relative(lexical)
    if relative is None:
        raise PermissionError(f"Path not allowed: {lexical}")
    if not relative:
        raise PermissionError("Path not allowed: the home directory itself cannot be modified")
    home = home_root()
    current = home
    for part in relative.split(os.sep):
        current = current / part
        try:
            info = os.lstat(current)
        except (FileNotFoundError, NotADirectoryError):
            break  # nothing below this point exists yet, so it cannot be a link
        except OSError:
            raise PermissionError("Path not allowed: the path cannot be inspected") from None
        if _is_link(info):
            raise PermissionError("Path not allowed: the path crosses a symbolic link or junction")
    return home / relative


def describe_target(operation: str, path: Any) -> str:
    """Target as the tool will resolve it, for the confirmation text.

    Returns ``"~/relative/path"``, ``"[refusé : …]"`` when the tool will refuse
    the path, or ``""`` when there is nothing to describe. Never raises.
    """
    if not isinstance(path, str) or not path:
        return ""
    if len(path) > _MAX_PATH_CHARS:
        return "[refusé : chemin trop long]"
    try:
        if operation in _READ_OPERATIONS:
            target = resolve_home_path(path)
        else:
            target = resolve_mutation_target(path)
        relative = target.relative_to(home_root()).as_posix()
    except PermissionError as exc:
        return f"[refusé : {exc}]"
    except Exception:
        return "[cible non vérifiable]"
    return "~" if relative == "." else f"~/{relative}"
