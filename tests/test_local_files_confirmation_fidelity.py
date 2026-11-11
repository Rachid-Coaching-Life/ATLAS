"""localFiles: the path confirmed is the path executed (relative paths, links, junctions)."""
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

from jarvis.tools import confirmation, local_paths
from jarvis.tools.base import ToolContext
from jarvis.tools.builtin import local_files
from jarvis.tools.builtin.local_files import LocalFilesTool

pytestmark = pytest.mark.unit

needs_symlinks = pytest.mark.skipif(
    not hasattr(os, "symlink"), reason="symbolic links are not available"
)


@pytest.fixture(autouse=True)
def _reset_provider():
    confirmation.set_provider(None)
    yield
    confirmation.set_provider(None)


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    elsewhere = tmp_path / "elsewhere"  # working directory outside the profile
    elsewhere.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original = os.path.expanduser
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(home) if p == "~" else original(p))
    monkeypatch.chdir(elsewhere)
    context = ToolContext(None, SimpleNamespace(), "", "", "", 0, lambda message: None)
    return SimpleNamespace(tool=LocalFilesTool(), context=context, home=home,
                           elsewhere=elsewhere, outside=outside)


def spelled(box, name, style):
    """Same file, written relative to home or as an absolute path."""
    return name if style == "relative" else str(box.home / name)


STYLES = pytest.mark.parametrize("style", ["relative", "absolute"])


def run(box, operation, path, **extra):
    return box.tool.run({"operation": operation, "path": path, **extra}, box.context)


def link(source, destination, directory=False):
    try:
        os.symlink(destination, source, target_is_directory=directory)
    except OSError:
        pytest.skip("symbolic links require a platform permission")


def execute(box, operation, path, **extra):
    """Through the real gate: Tool.execute() asks the registered provider."""
    return box.tool.execute(
        db=None, cfg=SimpleNamespace(), tool_args={"operation": operation, "path": path, **extra},
        system_prompt="", original_prompt="", redacted_text="", max_retries=0,
        user_print=lambda message: None,
    )


# ---------------------------------------------------------------- priority 1

def test_relative_paths_are_relative_to_home_when_cwd_is_outside(sandbox):
    (sandbox.home / "note.txt").write_text("home copy")
    (sandbox.elsewhere / "note.txt").write_text("cwd copy")
    assert run(sandbox, "read", "note.txt").reply_text == "home copy"
    assert run(sandbox, "write", "note.txt", content="changed").success
    assert (sandbox.home / "note.txt").read_text() == "changed"
    assert (sandbox.elsewhere / "note.txt").read_text() == "cwd copy"
    assert run(sandbox, "append", "note.txt", content="+").success
    assert (sandbox.home / "note.txt").read_text() == "changed+"
    assert run(sandbox, "delete", "note.txt").success
    assert not (sandbox.home / "note.txt").exists()
    assert (sandbox.elsewhere / "note.txt").read_text() == "cwd copy"


def test_relative_listing_is_relative_to_home(sandbox):
    (sandbox.home / "docs").mkdir()
    (sandbox.home / "docs" / "a.txt").write_text("a")
    result = run(sandbox, "list", "docs")
    assert result.success and "a.txt" in result.reply_text
    assert run(sandbox, "list", ".").success


def test_absolute_path_inside_profile_still_works(sandbox):
    target = sandbox.home / "abs.txt"
    assert run(sandbox, "write", str(target), content="one").success
    assert run(sandbox, "append", str(target), content="two").success
    assert run(sandbox, "read", str(target)).reply_text == "onetwo"
    assert run(sandbox, "delete", str(target)).success and not target.exists()


@pytest.mark.parametrize("operation", ["read", "write", "append", "delete"])
@pytest.mark.parametrize("style", ["absolute", "parent"])
def test_path_outside_profile_is_refused(sandbox, operation, style):
    victim = sandbox.outside / "victim.txt"
    victim.write_text("keep")
    path = str(victim) if style == "absolute" else "../outside/victim.txt"
    result = run(sandbox, operation, path, content="x")
    assert not result.success and "not allowed" in result.reply_text.lower()
    assert victim.read_text() == "keep"


def test_home_directory_itself_cannot_be_modified(sandbox):
    for operation in ("write", "append", "delete"):
        assert not run(sandbox, operation, "~", content="x").success
    assert sandbox.home.is_dir()


# ---------------------------------------------------------------- priority 2

@needs_symlinks
@STYLES
@pytest.mark.parametrize("operation", ["write", "append", "delete"])
def test_link_to_another_profile_file_is_refused(sandbox, operation, style):
    precious = sandbox.home / "precious.txt"
    precious.write_text("precious")
    link(sandbox.home / "alias.txt", precious)
    result = run(sandbox, operation, spelled(sandbox, "alias.txt", style), content="x")
    assert not result.success and "link" in result.reply_text.lower()
    assert precious.read_text() == "precious"
    assert (sandbox.home / "alias.txt").is_symlink()


@needs_symlinks
@STYLES
@pytest.mark.parametrize("operation", ["write", "append", "delete"])
def test_link_to_a_path_outside_profile_is_refused(sandbox, operation, style):
    victim = sandbox.outside / "victim.txt"
    victim.write_text("keep")
    link(sandbox.home / "escape.txt", victim)
    result = run(sandbox, operation, spelled(sandbox, "escape.txt", style), content="x")
    assert not result.success
    assert victim.read_text() == "keep"


@needs_symlinks
@STYLES
@pytest.mark.parametrize("operation", ["write", "append", "delete"])
def test_directory_link_component_is_refused(sandbox, operation, style):
    nested = sandbox.home / "nested"
    nested.mkdir()
    (nested / "inside.txt").write_text("inside")
    link(sandbox.home / "alias", nested, directory=True)
    result = run(sandbox, operation, spelled(sandbox, "alias/inside.txt", style), content="x")
    assert not result.success and "link" in result.reply_text.lower()
    assert (nested / "inside.txt").read_text() == "inside"
    assert not run(sandbox, "write", spelled(sandbox, "alias/new.txt", style), content="x").success
    assert not (nested / "new.txt").exists()


@needs_symlinks
def test_reading_through_an_in_profile_link_keeps_working(sandbox):
    (sandbox.home / "real.txt").write_text("content")
    link(sandbox.home / "alias.txt", sandbox.home / "real.txt")
    assert run(sandbox, "read", "alias.txt").reply_text == "content"


@pytest.mark.parametrize("tag, redirects", [
    (0xA0000003, True), (0xA000000C, True), (0x9000601A, False), (0, False),
])
def test_only_redirecting_reparse_points_count_as_links(tag, redirects):
    info = SimpleNamespace(st_mode=stat.S_IFDIR, st_reparse_tag=tag)
    assert local_paths._is_link(info) is redirects


@pytest.mark.skipif(os.name != "nt", reason="junctions exist on Windows only")
def test_windows_junction_is_refused(sandbox):
    nested = sandbox.home / "nested"
    nested.mkdir()
    (nested / "inside.txt").write_text("inside")
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(sandbox.home / "junction"), str(nested)],
                          capture_output=True)
    if made.returncode != 0:
        pytest.skip("mklink /J is not available")
    for operation in ("write", "append", "delete"):
        assert not run(sandbox, operation, "junction/inside.txt", content="x").success
    assert (nested / "inside.txt").read_text() == "inside"


# ----------------------------------------------- confirmed path == executed path

@pytest.mark.parametrize("given", [
    "concord.txt", "./concord.txt", "~/concord.txt", "sub/../concord.txt", "@ABSOLUTE@",
])
def test_confirmed_target_is_the_file_that_is_written(sandbox, given):
    (sandbox.home / "sub").mkdir()
    given = str(sandbox.home / "concord.txt") if given == "@ABSOLUTE@" else given
    shown = local_paths.describe_target("write", given)
    assert shown == "~/concord.txt"
    summary = confirmation.summarize("localFiles", {"operation": "write", "path": given, "content": "c"})
    assert "~/concord.txt" in summary
    assert run(sandbox, "write", given, content="c").success
    assert (sandbox.home / "concord.txt").read_text() == "c"


def test_nested_new_directories_match_the_confirmed_target(sandbox):
    assert local_paths.describe_target("write", "new/dir/x.txt") == "~/new/dir/x.txt"
    assert run(sandbox, "write", "new/dir/x.txt", content="c").success
    assert (sandbox.home / "new" / "dir" / "x.txt").read_text() == "c"


def test_summary_shows_the_real_target_of_a_relative_path(sandbox):
    summary = confirmation.summarize("localFiles", {"operation": "delete", "path": "note.txt"})
    assert summary == "localFiles : delete sur note.txt → ~/note.txt"


def test_summary_is_unchanged_when_the_path_is_already_canonical(sandbox):
    summary = confirmation.summarize("localFiles", {
        "operation": "write", "path": "~/a.txt", "content": "abc"})
    assert summary == "localFiles : write sur ~/a.txt (3 caractères)"


@needs_symlinks
def test_summary_marks_a_path_the_tool_will_refuse(sandbox):
    (sandbox.home / "precious.txt").write_text("p")
    link(sandbox.home / "alias.txt", sandbox.home / "precious.txt")
    summary = confirmation.summarize("localFiles", {"operation": "delete", "path": "~/alias.txt"})
    assert "[refusé" in summary and "link" in summary
    outside = confirmation.summarize("localFiles", {"operation": "write", "path": str(sandbox.outside / "x")})
    assert "[refusé" in outside


def test_describe_target_never_raises(sandbox):
    for path in (None, 12, [], "", "x" * 10000, "a\x00b", "\ud800"):
        assert isinstance(local_paths.describe_target("delete", path), str)


# ------------------------------------------------------------------- TOCTOU

@needs_symlinks
@pytest.mark.parametrize("operation", ["write", "delete"])
def test_link_created_while_the_user_confirms_is_refused(sandbox, operation):
    precious = sandbox.home / "precious.txt"
    precious.write_text("precious")
    target = sandbox.home / "doc.txt"
    target.write_text("doc")

    def approve_after_swap(request):
        target.unlink()
        os.symlink(precious, target)
        return True

    confirmation.set_provider(approve_after_swap)
    result = execute(sandbox, operation, str(target), content="overwritten")
    assert not result.success
    assert precious.read_text() == "precious"


@needs_symlinks
@pytest.mark.parametrize("nofollow", [True, False])
def test_link_swapped_in_between_check_and_open_is_not_followed(sandbox, monkeypatch, nofollow):
    precious = sandbox.home / "precious.txt"
    precious.write_text("precious")
    target = sandbox.home / "doc.txt"
    target.write_text("doc")
    if not nofollow:
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    real_open = os.open
    swapped = []

    def swap_then_open(path, *args, **kwargs):
        if os.fspath(path) == str(target) and not swapped:
            swapped.append(True)
            target.unlink()
            os.symlink(precious, target)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(local_files.os, "open", swap_then_open)
    result = run(sandbox, "write", str(target), content="overwritten")
    assert swapped and not result.success
    assert precious.read_text() == "precious"


@needs_symlinks
def test_link_swapped_in_just_before_delete_is_refused(sandbox, monkeypatch):
    precious = sandbox.home / "precious.txt"
    precious.write_text("precious")
    target = sandbox.home / "doc.txt"
    target.write_text("doc")
    real = local_paths.resolve_mutation_target
    calls = []

    def swap_after_first_check(path):
        calls.append(path)
        outcome = real(path)
        if len(calls) == 1:
            target.unlink()
            os.symlink(precious, target)
        return outcome

    monkeypatch.setattr(local_paths, "resolve_mutation_target", swap_after_first_check)
    result = run(sandbox, "delete", str(target))
    assert len(calls) == 2 and not result.success
    assert precious.read_text() == "precious"
    assert target.is_symlink()


# --------------------------------------------------------- non-regression

def test_read_and_list_keep_their_behaviour(sandbox):
    (sandbox.home / "a.txt").write_text("hello")
    (sandbox.home / "sub").mkdir()
    (sandbox.home / "sub" / "b.txt").write_text("b")
    assert run(sandbox, "read", "~/a.txt").reply_text == "hello"
    listing = run(sandbox, "list", "~", glob="*.txt")
    assert listing.success and "a.txt" in listing.reply_text
    assert "b.txt" in run(sandbox, "list", "~", glob="*.txt", recursive=True).reply_text


def test_pdf_search_keeps_its_behaviour(sandbox):
    (sandbox.home / "sub").mkdir()
    (sandbox.home / "sub" / "doc.pdf").write_bytes(b"%PDF-1.4")
    (sandbox.home / "note.txt").write_text("n")
    result = run(sandbox, "search", "~", file_type="pdf")
    assert result.success and "doc.pdf" in result.reply_text and "note.txt" not in result.reply_text
    assert not run(sandbox, "search", "~", file_type="docx").success
    assert not run(sandbox, "search", str(sandbox.outside), file_type="pdf").success


def test_write_keeps_text_semantics_and_replaces_content(sandbox):
    target = sandbox.home / "t.txt"
    target.write_text("a long previous content")
    assert run(sandbox, "write", "t.txt", content="café").success
    assert target.read_text(encoding="utf-8") == "café"
    assert run(sandbox, "append", "t.txt", content=" été").success
    assert target.read_text(encoding="utf-8") == "café été"
    assert run(sandbox, "append", "fresh.txt", content="new").success
    assert (sandbox.home / "fresh.txt").read_text() == "new"
