"""The migration script on a small synthetic repository (git required)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_to_atlas.py"
TEMPLATES = SCRIPT.parent / "atlas_migration"

pytestmark = [pytest.mark.unit, pytest.mark.skipif(shutil.which("git") is None, reason="git is required")]

NL = chr(10)


def L(*lines):
    return NL.join(lines) + NL


FILES = {
    "src/jarvis/__init__.py": L(
        '"""Jarvis voice assistant."""',
        "import os as _os",
        "from .config import load_settings",
        "__all__ = ['load_settings']",
    ),
    "src/jarvis/config.py": L(
        "import os",
        "JARVIS_DEBUG = os.environ.get('JARVIS_VOICE_DEBUG')",
        "class JarvisConfig:",
        "    name = 'Jarvis'",
        "    path = '.config/jarvis'",
        "# Upstream: https://github.com/isair/jarvis/issues",
        "# jarvice is a phonetic variant kept for review",
        "def load_settings():",
        "    jarvis_dir = os.path.expanduser('~/.local/share/jarvis')",
        "    return f'{jarvis_dir}/Jarvis says {JARVIS_DEBUG}'",
    ),
    "src/jarvis/tools/__init__.py": "",
    "src/jarvis/tools/y.py": L("def f():", "    return 'ok'"),
    "src/jarvis/tools/x.py": L(
        "from jarvis.tools import y",
        "import jarvis.tools.y as yy",
        "from jarvis import config",
        "def g():",
        "    return y.f(), yy.f(), config.JarvisConfig.name",
    ),
    "src/desktop_app/__init__.py": "",
    "src/desktop_app/app.py": L(
        "import subprocess, sys",
        "import jarvis",
        "def start():",
        "    return subprocess.run([sys.executable, '-m', 'jarvis.daemon'])",
    ),
    "jarvis_desktop.spec": L("a = Analysis(['src/jarvis/main.py'], hiddenimports=['jarvis.tools'])", "name = 'Jarvis'"),
    "installer/windows/jarvis_setup.iss": L('#define MyAppName "Jarvis"', "OutputBaseFilename=Jarvis-Setup-x64"),
    "scripts/run.sh": L("#!/bin/sh", "PYTHONPATH=src python -m jarvis.main"),
    "tests/test_config.py": L(
        "from jarvis.config import JarvisConfig, load_settings",
        "from jarvis.tools import x",
        "def test_a(monkeypatch):",
        "    monkeypatch.setattr('jarvis.tools.y.f', lambda: 'patched')",
        "    assert JarvisConfig.name == 'Jarvis'",
        "    assert x.g()[0] == 'patched'",
        "    assert 'Jarvis says' in load_settings()",
    ),
    "LICENSE": L("Copyright (c) 2025 isair", "Jarvis is free for personal use."),
    "README.md": L("# Jarvis", "See https://github.com/isair/jarvis for the original project.", "Run jarvis now."),
    ".github/workflows/t.yml": L("name: Jarvis tests", "jobs: {}"),
    "website/index.html": L("<h1>Jarvis</h1>"),
}


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def tool(repo, *args, expect=0):
    done = subprocess.run([sys.executable, str(repo / "scripts" / "migrate_to_atlas.py"), *args],
                          cwd=repo, capture_output=True, text=True)
    assert done.returncode == expect, done.stdout + done.stderr
    return done


@pytest.fixture
def repo(tmp_path):
    for rel, content in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (tmp_path / "scripts").mkdir(exist_ok=True)
    shutil.copy(SCRIPT, tmp_path / "scripts" / "migrate_to_atlas.py")
    shutil.copytree(TEMPLATES, tmp_path / "scripts" / "atlas_migration")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.org")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "baseline")
    return tmp_path


def reports(repo):
    return str(repo.parent / (repo.name + "-reports"))


def migrate(repo):
    tool(repo, "apply", "--report-dir", reports(repo), expect=0)
    git(repo, "add", "-A")


def test_inventory_changes_nothing(repo):
    before = git(repo, "status", "--porcelain")
    done = tool(repo, "inventory", "--out", reports(repo) + "/inv.json")
    assert "unmigrated/import" in done.stdout
    assert git(repo, "status", "--porcelain") == before


def test_package_files_and_paths_are_renamed_with_git(repo):
    migrate(repo)
    assert (repo / "src/atlas/config.py").is_file() and not (repo / "src/jarvis").exists()
    assert (repo / "atlas_desktop.spec").is_file() and not (repo / "jarvis_desktop.spec").exists()
    assert (repo / "installer/windows/atlas_setup.iss").is_file()
    status = git(repo, "status", "--porcelain")
    assert "R" in status


def test_imports_identifiers_strings_and_assertions(repo):
    migrate(repo)
    config = (repo / "src/atlas/config.py").read_text()
    assert "ATLAS_DEBUG = os.environ.get('ATLAS_VOICE_DEBUG')" in config
    assert "class AtlasConfig:" in config and "name = 'ATLAS'" in config
    assert "path = '.config/atlas'" in config and "atlas_dir = os.path.expanduser('~/.local/share/atlas')" in config
    assert "{atlas_dir}/ATLAS says {ATLAS_DEBUG}" in config
    assert "https://github.com/isair/jarvis/issues" in config
    code = (repo / "src/atlas/tools/x.py").read_text()
    assert "from atlas.tools import y" in code and "import atlas.tools.y as yy" in code
    assert "from atlas import config" in code and "config.AtlasConfig.name" in code
    assert "'-m', 'atlas.daemon'" in (repo / "src/desktop_app/app.py").read_text()
    test = (repo / "tests/test_config.py").read_text()
    assert "monkeypatch.setattr('atlas.tools.y.f'" in test
    assert test.count("assert ") == 3
    assert "assert AtlasConfig.name == 'ATLAS'" in test and "'ATLAS says' in load_settings()" in test
    spec = (repo / "atlas_desktop.spec").read_text()
    assert "src/atlas/main.py" in spec and "hiddenimports=['atlas.tools']" in spec and "name = 'ATLAS'" in spec
    assert "OutputBaseFilename=ATLAS-Setup-x64" in (repo / "installer/windows/atlas_setup.iss").read_text()
    assert "python -m atlas.main" in (repo / "scripts/run.sh").read_text()


def test_licence_attribution_workflow_and_website_are_preserved(repo):
    migrate(repo)
    assert (repo / "LICENSE").read_text() == FILES["LICENSE"]
    assert (repo / ".github/workflows/t.yml").read_text() == FILES[".github/workflows/t.yml"]
    assert (repo / "website/index.html").read_text() == FILES["website/index.html"]
    readme = (repo / "README.md").read_text()
    assert readme.startswith("# ATLAS") and "https://github.com/isair/jarvis" in readme and "Run atlas now." in readme


def test_legacy_layer_and_hook_are_installed_before_relative_imports(repo):
    migrate(repo)
    assert (repo / "src/atlas/legacy_compat.py").is_file()
    assert (repo / "tests/test_atlas_legacy_compat.py").is_file()
    init = (repo / "src/atlas/__init__.py").read_text().split(NL)
    hook = next(i for i, line in enumerate(init) if "legacy_compat.apply_env_aliases" in line)
    relative = next(i for i, line in enumerate(init) if line.startswith("from .config"))
    assert hook < relative


def test_migration_is_idempotent(repo):
    migrate(repo)
    git(repo, "commit", "-q", "-m", "migrated")
    done = tool(repo, "apply", "--report-dir", reports(repo) + "2")
    assert "renamed paths: 0; modified files: 0" in done.stdout
    assert git(repo, "status", "--porcelain").strip() == ""


def test_check_passes_after_migration_and_fails_before(repo):
    tool(repo, "check", "--skip-imports", expect=1)
    migrate(repo)
    done = tool(repo, "check", "--report-dir", reports(repo))
    assert "problems: 0" in done.stdout
    report = (Path(reports(repo)) / "check-report.json").read_text()
    assert "licence or third-party notice" in report and "workflow file" in report
    assert "jarvice" in report


def test_migrated_code_imports_and_tests_pass(repo):
    migrate(repo)
    env_check = tool(repo, "check", "--report-dir", reports(repo))
    assert "problems: 0" in env_check.stdout
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                          cwd=repo, capture_output=True, text=True, env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})
    assert done.returncode == 0, done.stdout + done.stderr


def test_compare_refuses_regressions_and_lost_tests(tmp_path):
    def junit(path, cases):
        body = "".join(
            f'<testcase classname="{c}" name="{n}">' + ("<failure/>" if bad else "") + "</testcase>"
            for c, n, bad in cases)
        path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    base, after = tmp_path / "b.xml", tmp_path / "a.xml"
    junit(base, [("tests.test_jarvis_x", "t1", True), ("tests.test_ok", "t2", False)])
    junit(after, [("tests.test_atlas_x", "t1", True), ("tests.test_ok", "t2", False)])
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), "compare", *a], capture_output=True, text=True)
    assert run(str(base), str(after)).returncode == 0
    junit(after, [("tests.test_atlas_x", "t1", True), ("tests.test_ok", "t2", True)])
    assert "REGRESSION: tests.test_ok::t2" in run(str(base), str(after)).stdout
    junit(after, [("tests.test_ok", "t2", False)])
    assert "FEWER TESTS" in run(str(base), str(after)).stdout
