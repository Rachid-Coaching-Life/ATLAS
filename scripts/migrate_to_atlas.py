#!/usr/bin/env python3
"""Deterministic migration of the Python engine from ``jarvis`` to ``atlas``.

Sub-commands (standard library only):

* ``inventory``       count every reference to the former name, change nothing;
* ``apply``           ``git mv`` paths, rewrite imports / identifiers / strings with
                      the tokenizer (no blind text replacement of code), install the
                      legacy-compatibility module and its hook, write a report;
* ``check``           fail on any reference that is not a justified exception, on
                      files that do not compile and on modules that do not import;
* ``junit-failures``  list the failing tests of a JUnit file;
* ``compare``         refuse regressions against a baseline taken before migrating;
* ``summary``         build the Markdown report of a CI run.

Licences, copyright and upstream attribution lines are never rewritten. Git
history is kept by using ``git mv``. Assertions are never touched: only names
are renamed, consistently, in code, tests and configuration.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import io
import json
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import tokenize
import xml.etree.ElementTree as ET
from pathlib import Path

NL = chr(10)
HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "atlas_migration"
TEXT_SUFFIXES = {
    ".py", ".pyi", ".spec", ".md", ".rst", ".txt", ".toml", ".ini", ".cfg", ".yml",
    ".yaml", ".json", ".sh", ".ps1", ".bat", ".cmd", ".iss", ".plist", ".desktop",
    ".html", ".css", ".js", ".mjs", ".xml", ".in", ".svg", ".manifest", ".rc",
}
TEXT_NAMES = {"Makefile", "Dockerfile", ".gitignore", ".gitattributes", ".releaserc.json"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock"}
TOOLING = {
    "scripts/migrate_to_atlas.py": "migration tooling (names the former name by design)",
    "tests/test_atlas_migration_script.py": "tests of the migration tooling",
    "src/atlas/legacy_compat.py": "legacy compatibility layer (reads the former names on purpose)",
    "tests/test_atlas_legacy_compat.py": "tests of the legacy compatibility layer",
}
KEEP_LINE = re.compile(
    "github[.]com/isair|barissencan|baris@|ko-fi[.]com/isair|sponsors/isair|copyright|"
    "[(]c[)] [0-9]|spdx-license-identifier|isair/jarvis",
    re.IGNORECASE,
)
UPSTREAM_ID = re.compile("(?<![A-Za-z])isair(?![A-Za-z])", re.IGNORECASE)
ANY_FORM = re.compile("jarvi", re.IGNORECASE)
EXACT_FORM = re.compile("jarvis", re.IGNORECASE)

# Order matters. The product name in prose becomes ATLAS, identifiers use Atlas.
TEXT_RULES = [
    (re.compile("JARVIS(?=_)"), "ATLAS"),
    (re.compile("(?<![A-Za-z])JARVIS(?![A-Za-z])"), "ATLAS"),
    (re.compile("Jarvis(?=[A-Z])"), "Atlas"),
    (re.compile("(?<=[a-z])Jarvis"), "Atlas"),
    (re.compile("(?<![A-Za-z])Jarvis(?![A-Za-z])"), "ATLAS"),
    (re.compile("(?<![A-Za-z])jarvis(?![a-z])"), "atlas"),
]


def text_name(value: str) -> str:
    """Rewrite names in prose, strings, paths and file names."""
    for pattern, replacement in TEXT_RULES:
        value = pattern.sub(replacement, value)
    return value


def ident_name(value: str) -> str:
    """Rewrite one Python identifier (the same way everywhere in the code base)."""
    return value.replace("JARVIS", "ATLAS").replace("Jarvis", "Atlas").replace("jarvis", "atlas")


def keep_line(line: str) -> bool:
    return bool(KEEP_LINE.search(line))


# --------------------------------------------------------------------- files

def run(args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def tracked_files(root: Path) -> list:
    out = run(["git", "ls-files", "-z"], root).stdout
    return sorted(item for item in out.split(chr(0)) if item)


def protected_reason(rel: str, workflows: bool = False, website: bool = False):
    if rel in TOOLING:
        return TOOLING[rel]
    if rel.startswith("scripts/atlas_migration/"):
        return "migration templates (name the former name by design)"
    name = rel.rsplit("/", 1)[-1]
    upper = name.upper()
    if upper.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "THIRD_PARTY", "THIRD-PARTY")):
        return "licence or third-party notice"
    if "/licenses/" in "/" + rel.lower() or "/licences/" in "/" + rel.lower():
        return "licence or third-party notice"
    if upper.startswith(("CHANGELOG", "RELEASE_NOTES", "HISTORY")):
        return "historical record"
    if rel.startswith("docs/atlas-migration/"):
        return "migration reports"
    if rel.startswith(".github/workflows/") and not workflows:
        return "workflow file: GITHUB_TOKEN cannot push workflow changes, migrate it separately"
    if rel.startswith("website/") and not website:
        return "public upstream website, separate deliverable: owner decision"
    if name in SKIP_NAMES:
        return "lock file"
    return None


def is_text_candidate(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name in TEXT_NAMES or Path(name).suffix.lower() in TEXT_SUFFIXES


def read_text(path: Path):
    data = path.read_bytes()
    if chr(0).encode() in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def write_text(path: Path, value: str) -> None:
    path.write_bytes(value.encode("utf-8"))


# ------------------------------------------------------------ python rewrite

def python_tokens(source: str):
    return list(tokenize.generate_tokens(io.StringIO(source).readline))


def _offsets(source: str):
    lines = io.StringIO(source).readlines()
    starts, total = [], 0
    for line in lines:
        starts.append(total)
        total += len(line)
    return lines, starts


def _string_like(kind: int) -> bool:
    return kind in (tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", -1), tokenize.COMMENT)


def _rewrite_slice(piece: str, lines: list, first_row: int) -> str:
    """Rewrite a string or comment slice line by line, skipping attribution lines."""
    out = []
    for index, segment in enumerate(piece.split(NL)):
        row = first_row - 1 + index
        physical = lines[row] if row < len(lines) else segment
        out.append(segment if keep_line(physical) else text_name(segment))
    return NL.join(out)


def transform_python(source: str):
    """Return (new source, conflicts). Raises SyntaxError if either side is invalid."""
    ast.parse(source)
    lines, starts = _offsets(source)
    tokens = python_tokens(source)
    names = {token.string for token in tokens if token.type == tokenize.NAME}
    conflicts, edits = [], []
    for token in tokens:
        if not ANY_FORM.search(token.string):
            continue
        (srow, scol), (erow, ecol) = token.start, token.end
        begin, end = starts[srow - 1] + scol, starts[erow - 1] + ecol
        if token.type == tokenize.NAME:
            new = ident_name(token.string)
            if new != token.string:
                if new in names:
                    conflicts.append(f"{token.string} -> {new} already exists")
                edits.append((begin, end, new))
        elif _string_like(token.type):
            piece = source[begin:end]
            expected = token.string
            if token.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
                piece_cmp = piece.replace("{{", "{").replace("}}", "}")
            else:
                piece_cmp = piece
            if piece_cmp != expected:
                raise SyntaxError(f"token offsets disagree with the source at line {srow}")
            new = _rewrite_slice(piece, lines, srow)
            if new != source[begin:end]:
                edits.append((begin, end, new))
    for begin, end, new in sorted(edits, reverse=True):
        source = source[:begin] + new + source[end:]
    ast.parse(source)
    return source, conflicts


def transform_plain(source: str) -> str:
    return NL.join(line if keep_line(line) else text_name(line) for line in source.split(NL))


# ------------------------------------------------------------------ renaming

def plan_roots(files: list) -> list:
    roots = []
    for rel in files:
        parts = rel.split("/")
        for index, part in enumerate(parts):
            if ANY_FORM.search(part):
                root = "/".join(parts[: index + 1])
                if root not in roots:
                    roots.append(root)
                break
    return roots


def perform_renames(root: Path, workflows: bool, website: bool, report: dict) -> dict:
    """git mv every path that carries the former name. Returns old -> new files."""
    moved = {}
    for _ in range(8):
        files = tracked_files(root)
        eligible = [f for f in files if protected_reason(f, workflows, website) is None]
        roots = plan_roots(eligible)
        if not roots:
            break
        progressed = False
        for old in roots:
            new = "/".join(old.split("/")[:-1] + [text_name(old.split("/")[-1])])
            under = [f for f in files if f == old or f.startswith(old + "/")]
            blocked = [f for f in under if protected_reason(f, workflows, website)]
            if new == old or blocked or (root / new).exists():
                report["problems"].append(f"cannot rename {old} -> {new} (blocked: {blocked[:3]})")
                continue
            (root / new).parent.mkdir(parents=True, exist_ok=True)
            run(["git", "mv", old, new], root)
            progressed = True
            for f in under:
                moved[f] = new + f[len(old):]
        if not progressed:
            break
    flat = {}
    for old, new in moved.items():
        while new in moved and moved[new] != new:
            new = moved[new]
        flat[old] = new
    return flat


# ----------------------------------------------------------- legacy support

HOOK_MARK = "atlas legacy hook"
HOOK_LINES = [
    "# atlas legacy hook: accept former environment variables and copy user data once",
    "from . import legacy_compat as _legacy_compat",
    "_legacy_compat.apply_env_aliases()",
    "_legacy_compat.migrate_user_data()",
    "del _legacy_compat",
]


def inject_hook(root: Path, report: dict) -> bool:
    """Insert the legacy hook before the first relative import of atlas/__init__.py."""
    path = root / "src" / "atlas" / "__init__.py"
    if not path.is_file():
        report["problems"].append("src/atlas/__init__.py not found: hook not installed")
        return False
    source = read_text(path) or ""
    if HOOK_MARK in source:
        return False
    newline = chr(13) + NL if (chr(13) + NL) in source else NL
    lines = source.split(NL)
    target = None
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.level >= 1:
            target = node.lineno - 1
            break
    block = [line + (chr(13) if newline != NL else "") for line in HOOK_LINES]
    if target is None:
        report["problems"].append("no relative import in atlas/__init__.py: hook appended at the end")
        lines = lines + block
    else:
        lines = lines[:target] + block + lines[target:]
    write_text(path, NL.join(lines))
    return True


def install_templates(root: Path, report: dict) -> list:
    written = []
    for template, target in (
        ("legacy_compat.py.tmpl", "src/atlas/legacy_compat.py"),
        ("test_atlas_legacy_compat.py.tmpl", "tests/test_atlas_legacy_compat.py"),
    ):
        source = TEMPLATES / template
        if not source.is_file():
            report["problems"].append(f"missing template {template}")
            continue
        destination = root / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        if not destination.exists() or destination.read_bytes() != content:
            destination.write_bytes(content)
            written.append(target)
    return written


# ----------------------------------------------------------------- inventory

def classify_python(source: str):
    """Yield (category, line number, text) for each reference in a Python file."""
    lines = io.StringIO(source).readlines()
    for token in python_tokens(source):
        if not ANY_FORM.search(token.string):
            continue
        row = token.start[0]
        text = lines[row - 1].strip() if row - 1 < len(lines) else ""
        if token.type == tokenize.NAME:
            kind = "import" if text.startswith(("import ", "from ")) else "identifier"
        elif token.type == tokenize.COMMENT:
            kind = "comment"
        else:
            kind = "string"
        yield kind, row, text


def scan_references(root: Path, workflows: bool = False, website: bool = False) -> dict:
    """Every reference to the former name, grouped. Used by inventory and check."""
    found = {"files": {}, "names": [], "excepted": [], "skipped_binary": []}
    for rel in tracked_files(root):
        if ANY_FORM.search(rel):
            reason = protected_reason(rel, workflows, website)
            found["names"].append({"path": rel, "exception": reason})
        reason = protected_reason(rel, workflows, website)
        path = root / rel
        if not path.is_file() or not (reason or is_text_candidate(rel)):
            continue
        source = read_text(path)
        if source is None:
            found["skipped_binary"].append(rel)
            continue
        if not ANY_FORM.search(source):
            continue
        if reason:
            found["excepted"].append({"path": rel, "reason": reason,
                                      "lines": sum(1 for l in source.split(NL) if ANY_FORM.search(l))})
            continue
        entries = []
        if rel.endswith((".py", ".pyi", ".spec")):
            try:
                for kind, row, text in classify_python(source):
                    entries.append({"kind": kind, "line": row, "text": text[:160]})
            except (SyntaxError, tokenize.TokenError):
                entries = []
        if not entries:
            for number, line in enumerate(source.split(NL), 1):
                if ANY_FORM.search(line):
                    entries.append({"kind": "text", "line": number, "text": line.strip()[:160]})
        for entry in entries:
            if keep_line(entry["text"]) or keep_line(source.split(NL)[entry["line"] - 1]):
                entry["category"] = "attribution"
            elif EXACT_FORM.search(entry["text"]) or EXACT_FORM.search(source.split(NL)[entry["line"] - 1]):
                entry["category"] = "unmigrated"
            else:
                entry["category"] = "variant-review"
        found["files"][rel] = entries
    return found


def summarize_scan(found: dict) -> dict:
    counts = {}
    for entries in found["files"].values():
        for entry in entries:
            key = f"{entry['category']}/{entry['kind']}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def cmd_inventory(args) -> int:
    root = Path(args.root).resolve()
    found = scan_references(root, args.workflows, args.website)
    report = {"counts": summarize_scan(found), "files": {k: len(v) for k, v in found["files"].items()},
              "names": found["names"], "excepted": found["excepted"],
              "skipped_binary": found["skipped_binary"], "detail": found["files"]}
    write_report(args.out, report)
    print(json.dumps(report["counts"], indent=2, sort_keys=True))
    print(f"files with references: {len(found['files'])}; excepted files: {len(found['excepted'])}")
    return 0


def write_report(out, report: dict) -> None:
    if not out:
        return
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------- apply

def cmd_apply(args) -> int:
    root = Path(args.root).resolve()
    if not args.allow_dirty and run(["git", "status", "--porcelain"], root).stdout.strip():
        print("working tree is not clean (use --allow-dirty)", file=sys.stderr)
        return 2
    report = {"problems": [], "conflicts": [], "modified": [], "renamed": {}, "installed": []}
    before = summarize_scan(scan_references(root, args.workflows, args.website))
    report["before"] = before
    report["renamed"] = perform_renames(root, args.workflows, args.website, report)
    for rel in tracked_files(root):
        if protected_reason(rel, args.workflows, args.website) or not is_text_candidate(rel):
            continue
        path = root / rel
        if not path.is_file():
            continue
        source = read_text(path)
        if source is None or not ANY_FORM.search(source):
            continue
        try:
            if rel.endswith((".py", ".pyi", ".spec")):
                new, conflicts = transform_python(source)
                report["conflicts"] += [f"{rel}: {c}" for c in conflicts]
            else:
                new = transform_plain(source)
        except (SyntaxError, tokenize.TokenError) as error:
            if rel.endswith((".spec",)):
                new = transform_plain(source)
            else:
                report["problems"].append(f"{rel}: not rewritten ({error})")
                continue
        if new != source:
            write_text(path, new)
            report["modified"].append(rel)
    if (root / "src" / "atlas").is_dir():
        report["installed"] += install_templates(root, report)
        if inject_hook(root, report):
            report["installed"].append("src/atlas/__init__.py (legacy hook)")
    after = scan_references(root, args.workflows, args.website)
    report["after"] = summarize_scan(after)
    write_report(Path(args.report_dir) / "apply-report.json" if args.report_dir else None, report)
    print(f"renamed paths: {len(report['renamed'])}; modified files: {len(report['modified'])}; "
          f"installed: {report['installed']}")
    for kind in ("problems", "conflicts"):
        for item in report[kind]:
            print(f"{kind[:-1].upper()}: {item}", file=sys.stderr)
    return 1 if report["problems"] or report["conflicts"] else 0


# --------------------------------------------------------------------- check

def import_report(root: Path, problems: list, warnings: list) -> dict:
    """Import every module of the new packages; the old package must be gone."""
    os.environ["ATLAS_SKIP_LEGACY_MIGRATION"] = "1"
    sys.path.insert(0, str(root / "src"))
    importlib.invalidate_caches()
    results = {"ok": [], "warn": [], "fail": []}
    if importlib.util.find_spec("jarvis") is not None:
        problems.append("the former package 'jarvis' is still importable")
    for top in ("atlas", "desktop_app"):
        if not (root / "src" / top).is_dir():
            if top == "atlas":
                problems.append("src/atlas does not exist")
            continue
        names = [top]
        failed = []
        walker = pkgutil.walk_packages([str(root / "src" / top)], top + ".", onerror=failed.append)
        names += [m.name for m in walker if not m.name.endswith(".__main__")]
        for name in names:
            try:
                importlib.import_module(name)
                results["ok"].append(name)
            except ModuleNotFoundError as error:
                missing = (error.name or "").split(".")[0]
                bucket = "fail" if missing in ("atlas", "jarvis", "desktop_app") else "warn"
                results[bucket].append(f"{name}: {error}")
            except BaseException as error:  # noqa: BLE001 - SystemExit from version guards, native libs
                results["warn"].append(f"{name}: {type(error).__name__}: {error}")
    for item in results["fail"]:
        problems.append(f"import failure caused by the rename: {item}")
    for item in results["warn"]:
        warnings.append(f"import not verifiable on this runner: {item}")
    return results


def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    problems, warnings = [], []
    found = scan_references(root, args.workflows, args.website)
    unmigrated = [(rel, e) for rel, entries in found["files"].items() for e in entries
                  if e["category"] == "unmigrated"]
    review = [(rel, e) for rel, entries in found["files"].items() for e in entries
              if e["category"] == "variant-review"]
    for rel, entry in unmigrated:
        problems.append(f"unmigrated reference {rel}:{entry['line']} ({entry['kind']}): {entry['text']}")
    for item in found["names"]:
        if not item["exception"]:
            problems.append(f"file name still carries the former name: {item['path']}")
    for rel in tracked_files(root):
        if rel.endswith(".py") and not protected_reason(rel, args.workflows, args.website):
            source = read_text(root / rel) or ""
            try:
                tree = ast.parse(source, rel)
            except SyntaxError as error:
                problems.append(f"{rel}: does not compile ({error})")
                continue
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules = [node.module]
                if any(m.split(".")[0] == "jarvis" for m in modules):
                    problems.append(f"{rel}:{node.lineno}: still imports the former package")
    imports = {}
    if not args.skip_imports:
        imports = import_report(root, problems, warnings)
    for rel, entry in review:
        warnings.append(f"to review (spelling variant) {rel}:{entry['line']}: {entry['text']}")
    exceptions = [{"path": e["path"], "reason": e["reason"], "lines": e["lines"]} for e in found["excepted"]]
    attributions = {rel: sum(1 for e in entries if e["category"] == "attribution")
                    for rel, entries in found["files"].items() if any(e["category"] == "attribution" for e in entries)}
    upstream = []
    for rel in tracked_files(root):
        if is_text_candidate(rel) and not protected_reason(rel, args.workflows, args.website):
            text = read_text(root / rel) or ""
            for number, line in enumerate(text.split(NL), 1):
                if UPSTREAM_ID.search(line) and not keep_line(line):
                    upstream.append(f"{rel}:{number}: {line.strip()[:120]}")
    for item in upstream:
        warnings.append(f"upstream identifier left for an owner decision {item}")
    report = {"problems": problems, "warnings": warnings, "exceptions": exceptions,
              "attribution_lines": attributions, "imports": {k: len(v) for k, v in imports.items()},
              "counts": summarize_scan(found)}
    write_report(Path(args.report_dir) / "check-report.json" if args.report_dir else None, report)
    print(f"problems: {len(problems)}; warnings: {len(warnings)}; excepted files: {len(exceptions)}")
    for item in problems:
        print("PROBLEM:", item, file=sys.stderr)
    return 1 if problems else 0


# ------------------------------------------------------------- test results

def junit_cases(path: str):
    tree = ET.parse(path)
    total, failing = 0, []
    for case in tree.iter("testcase"):
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failing.append(f"{case.get('classname')}::{case.get('name')}")
    return total, sorted(set(failing))


def cmd_junit_failures(args) -> int:
    total, failing = junit_cases(args.junit)
    print(NL.join(failing))
    print(f"total={total} failing={len(failing)}", file=sys.stderr)
    return 0


def cmd_compare(args) -> int:
    base_total, base_failing = junit_cases(args.baseline)
    new_total, new_failing = junit_cases(args.after)
    expected = {text_name(item) for item in base_failing}
    regressions = sorted(set(new_failing) - expected)
    print(f"baseline: {base_total} tests, {len(base_failing)} failing")
    print(f"after:    {new_total} tests, {len(new_failing)} failing")
    for item in regressions:
        print("REGRESSION:", item)
    status = 0
    if regressions:
        status = 1
    if new_total < base_total:
        print(f"FEWER TESTS COLLECTED: {new_total} < {base_total}")
        status = 1
    return status


# ------------------------------------------------------------------- summary

def tail(path: Path, count: int = 60) -> str:
    if not path.is_file():
        return "(missing)"
    return NL.join(path.read_text(encoding="utf-8", errors="replace").split(NL)[-count:])


def cmd_summary(args) -> int:
    reports = Path(args.reports)
    results = json.loads(os.environ.get("JOB_RESULTS", "{}"))
    out = ["# Migration jarvis -> atlas: dernier run automatise", "", "| Etape | Resultat |", "| --- | --- |"]
    out += [f"| {name} | {value.get('result', value) if isinstance(value, dict) else value} |"
            for name, value in sorted(results.items())]
    for title, filename in (("Application", "apply-report.json"), ("Verification", "check-report.json")):
        path = reports / filename
        out += ["", f"## {title}", ""]
        if not path.is_file():
            out.append("(rapport absent)")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("problems", "conflicts", "warnings"):
            items = data.get(key) or []
            out.append(f"- {key}: {len(items)}")
            out += [f"  - {item}" for item in items[:40]]
        if "renamed" in data:
            out.append(f"- chemins renommes: {len(data['renamed'])}; fichiers modifies: {len(data.get('modified', []))}")
        if "exceptions" in data:
            out.append("- exceptions justifiees:")
            out += [f"  - {e['path']} ({e['lines']} lignes): {e['reason']}" for e in data["exceptions"]]
    for title, filename in (("Comparaison des tests", "compare.log"), ("Tests apres migration (fin du journal)", "after-tests.log"),
                            ("Tests avant migration (fin du journal)", "baseline-tests.log"),
                            ("Windows (fin du journal)", "windows.log")):
        out += ["", f"## {title}", "", "```", tail(reports / filename), "```"]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(NL.join(out) + NL, encoding="utf-8")
    return 0


# ---------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--root", default=".")
        p.add_argument("--workflows", action="store_true", help="also migrate .github/workflows")
        p.add_argument("--website", action="store_true", help="also migrate website/")

    inv = sub.add_parser("inventory")
    common(inv)
    inv.add_argument("--out")
    inv.set_defaults(func=cmd_inventory)
    app = sub.add_parser("apply")
    common(app)
    app.add_argument("--report-dir")
    app.add_argument("--allow-dirty", action="store_true")
    app.set_defaults(func=cmd_apply)
    chk = sub.add_parser("check")
    common(chk)
    chk.add_argument("--report-dir")
    chk.add_argument("--skip-imports", action="store_true")
    chk.set_defaults(func=cmd_check)
    jf = sub.add_parser("junit-failures")
    jf.add_argument("junit")
    jf.set_defaults(func=cmd_junit_failures)
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("baseline")
    cmp_.add_argument("after")
    cmp_.set_defaults(func=cmd_compare)
    summ = sub.add_parser("summary")
    summ.add_argument("--reports", required=True)
    summ.add_argument("--out", required=True)
    summ.set_defaults(func=cmd_summary)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
