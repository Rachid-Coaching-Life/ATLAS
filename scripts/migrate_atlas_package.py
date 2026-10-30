"""Controlled ATLAS package migration. Plan by default; --apply requires clean develop-atlas."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import subprocess

OLD = "jar" + "vis"
NEW = "atlas"
ROOTS = ("src/", "tests/", "evals/", "scripts/", "installer/", ".github/")
SUFFIXES = (".py", ".pyi", ".spec", ".ps1", ".bat", ".sh", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".iss")
SPECIAL = ("jarvis_desktop.spec", "setup.py", "setup.cfg", "pytest.ini")
DOTTED = re.compile(r"(?<![A-Za-z0-9_./\\\\])" + OLD + r"(?=\.)")
IMPORT = re.compile(r"(?m)\b(from|import)\s+" + OLD + r"(?=\s|$)")
PKGPATH = re.compile(r"src[/\\]" + OLD + r"(?=[/\\])")
BARE_SPEC = re.compile(r"(['\"])" + OLD + r"\1")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def rewrite(path, source):
    target = DOTTED.sub(NEW, source)
    target = IMPORT.sub(lambda m: m[1] + " " + NEW, target)
    target = PKGPATH.sub("src/" + NEW, target)
    if path.endswith(".spec"):
        target = BARE_SPEC.sub(lambda m: m[1] + NEW + m[1], target)
        # Packaging output names belong to the new application, not its data.
        target = target.replace("name='Jarvis'", "name='ATLAS'")
        target = target.replace("name='Jarvis.app'", "name='ATLAS.app'")
    if path.endswith(".iss"):
        # Only the installer/build contract changes here. Do not touch the
        # application GUID, persistent folders, or user configuration paths.
        target = target.replace('#define MyAppName "Jarvis"', '#define MyAppName "ATLAS"')
        target = target.replace('#define MyAppExeName "Jarvis.exe"', '#define MyAppExeName "ATLAS.exe"')
        target = target.replace('OutputBaseFilename=Jarvis-Setup-x64', 'OutputBaseFilename=ATLAS-Setup-x64')
        target = target.replace("dist" + chr(92) + "Jarvis" + chr(92), "dist" + chr(92) + "ATLAS" + chr(92))
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="rewrite files after safety checks")
    args = parser.parse_args()
    if Path.cwd().resolve() != Path(__file__).resolve().parents[1]:
        parser.error("Run from the repository root")
    if git("branch", "--show-current") != "develop-atlas":
        parser.error("Only develop-atlas is allowed")
    dirty = set(git("diff", "--name-only").splitlines()) | set(git("diff", "--cached", "--name-only").splitlines())
    affected_dirty = sorted(path for path in dirty if
        (path.startswith(ROOTS) or path in SPECIAL) and
        (path.endswith(SUFFIXES) or path in SPECIAL))
    if affected_dirty:
        parser.error("Tracked migration inputs have local edits: " + ", ".join(affected_dirty))
    if not Path("src", OLD).is_dir() or Path("src", NEW).exists():
        parser.error("Source package missing or destination already present")

    changes = []
    for path in git("ls-files").splitlines():
        if not (path.startswith(ROOTS) or path in SPECIAL):
            continue
        if not (path.endswith(SUFFIXES) or path in SPECIAL):
            continue
        p = Path(path)
        try:
            raw = p.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError) as e:
            parser.error(f"Cannot inspect {path}: {e}")
        new_path = path.replace("src/" + OLD + "/", "src/" + NEW + "/", 1) if path.startswith("src/" + OLD + "/") else path
        transformed = rewrite(path, raw)
        if new_path != path or transformed != raw:
            changes.append((path, new_path, transformed))

    print(f"Planned changed files: {len(changes)}")
    for old, new, _ in changes:
        print(f"  {old}" + (f" -> {new}" if new != old else ""))
    if not args.apply:
        print("DRY RUN ONLY: no changes made")
        return
    for old, new, _ in changes:
        if old != new and Path(new).exists():
            parser.error(f"Destination already exists: {new}")
    for _, new, content in changes:
        dest = Path(new)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    for old, new, _ in changes:
        if new != old:
            Path(old).unlink()
    print("Changes made locally. Review diff and run tests before committing.")


if __name__ == "__main__":
    main()
