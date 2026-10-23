import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import release_shared as rs  # noqa: E402


class TestVersions:
    @pytest.mark.parametrize(
        ("bump", "expected"),
        [("patch", (0, 2, 1)), ("minor", (0, 3, 0)), ("major", (1, 0, 0)), ("0.4.2", (0, 4, 2))],
    )
    def test_next_version(self, bump, expected):
        assert rs.next_version((0, 2, 0), bump) == expected

    @pytest.mark.parametrize("bump", ["0.2.0", "0.1.9", "banana", "1.2"])
    def test_refuses_a_version_that_is_not_newer_or_not_a_version(self, bump):
        with pytest.raises(rs.ReleaseError):
            rs.next_version((0, 2, 0), bump)

    def test_rewrites_both_version_strings(self):
        pyproject = '[project]\nname = "shared"\nversion = "0.2.0"\n'
        init = '__version__ = "0.2.0"\n'

        assert 'version = "0.3.0"' in rs.set_pyproject_version(pyproject, (0, 3, 0))
        assert rs.set_init_version(init, (0, 3, 0)) == '__version__ = "0.3.0"\n'
        assert rs.read_version(pyproject) == (0, 2, 0)


class TestServiceRanges:
    TEXT = 'dependencies = [\n    "shared[drf,wp]>=0.2,<0.3",\n    "django>=5.2,<5.3",\n]\n'

    def test_a_patch_inside_the_range_changes_nothing(self):
        assert rs.widen_service_range(self.TEXT, (0, 2, 1)) == (self.TEXT, False)

    def test_a_breaking_0x_minor_moves_the_range_and_keeps_the_extras(self):
        text, changed = rs.widen_service_range(self.TEXT, (0, 3, 0))

        assert changed
        assert '"shared[drf,wp]>=0.3,<0.4"' in text
        assert '"django>=5.2,<5.3"' in text

    def test_a_major_release_gets_a_major_range(self):
        text, _ = rs.widen_service_range('"shared[wp]>=0.2,<0.3"', (1, 0, 0))

        assert text == '"shared[wp]>=1.0,<2.0"'


class FakeRunner:
    """Answers git the way a clean, up-to-date main does; records every command."""

    def __init__(self, *, dirty=False, branch="main", behind=False, tag_exists=False):
        self.calls = []
        self.dirty, self.branch, self.behind, self.tag_exists = dirty, branch, behind, tag_exists
        self.files_changed = False

    def run(self, *cmd, capture=False):
        self.calls.append(cmd)
        if cmd[:3] == ("git", "status", "--porcelain"):
            if self.dirty:
                return " M something.py\n"
            return " M libs/shared/pyproject.toml\n" if self.files_changed else ""
        if cmd[:2] == ("git", "rev-parse"):
            if "--abbrev-ref" in cmd:
                return self.branch + "\n"
            return ("bbb" if self.behind and cmd[2] != "HEAD" else "aaa") + "\n"
        if cmd[:3] == ("git", "tag", "--list"):
            return cmd[3] + "\n" if self.tag_exists else ""
        if cmd[:2] == ("uv", "lock"):
            self.files_changed = True
        return ""

    def ran(self, *prefix):
        return any(call[: len(prefix)] == prefix for call in self.calls)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A copy of the files the release touches, in a temporary directory."""
    lib = tmp_path / "libs/shared"
    (lib / "src/shared").mkdir(parents=True)
    (lib / "pyproject.toml").write_text('[project]\nname = "shared"\nversion = "0.2.0"\n')
    (lib / "src/shared/__init__.py").write_text('__version__ = "0.2.0"\n')
    for service, extras in (("app", "drf,wp"), ("auth", "wp")):
        (tmp_path / f"services/{service}").mkdir(parents=True)
        (tmp_path / f"services/{service}/pyproject.toml").write_text(
            f'dependencies = ["shared[{extras}]>=0.2,<0.3"]\n'
        )
    (tmp_path / "uv.lock").write_text("lock v0.2.0\n")
    monkeypatch.setattr(rs, "ROOT", tmp_path)
    monkeypatch.setattr(rs, "LIB_PYPROJECT", lib / "pyproject.toml")
    monkeypatch.setattr(rs, "LIB_INIT", lib / "src/shared/__init__.py")
    monkeypatch.setattr(rs, "LOCKFILE", tmp_path / "uv.lock")
    return tmp_path


def snapshot(root):
    return {p: p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


class TestRelease:
    def test_a_minor_release_bumps_widens_commits_tags_and_pushes(self, repo):
        runner = FakeRunner()

        tag = rs.release(["minor", "--yes"], runner)

        assert tag == "shared/v0.3.0"
        assert 'version = "0.3.0"' in (repo / "libs/shared/pyproject.toml").read_text()
        assert '"0.3.0"' in (repo / "libs/shared/src/shared/__init__.py").read_text()
        assert ">=0.3,<0.4" in (repo / "services/app/pyproject.toml").read_text()
        assert runner.ran("uv", "lock")
        assert runner.ran("uv", "run", "--package", "shared")
        assert runner.ran("git", "commit", "--quiet", "-m", "shared 0.3.0")
        assert runner.ran("git", "tag", "-a", "shared/v0.3.0")
        assert runner.ran("git", "push", "--atomic", "origin", "main", "shared/v0.3.0")

    def test_a_dry_run_changes_nothing(self, repo):
        before = snapshot(repo)
        runner = FakeRunner()

        rs.release(["minor", "--dry-run"], runner)

        assert snapshot(repo) == before
        assert not runner.ran("git", "commit") and not runner.ran("git", "push")

    def test_declining_restores_every_file(self, repo):
        before = snapshot(repo)

        with pytest.raises(rs.ReleaseError, match="not released"):
            rs.release(["patch"], FakeRunner(), ask=lambda _: "n")

        assert snapshot(repo) == before

    def test_tag_current_tags_without_bumping(self, repo):
        before = snapshot(repo)
        runner = FakeRunner()

        assert rs.release(["--tag-current", "--yes"], runner) == "shared/v0.2.0"
        assert snapshot(repo) == before
        assert not runner.ran("git", "commit")
        assert runner.ran("git", "push", "--atomic", "origin", "main", "shared/v0.2.0")

    @pytest.mark.parametrize(
        ("runner", "message"),
        [
            (FakeRunner(dirty=True), "working tree has changes"),
            (FakeRunner(branch="feature"), "releases are cut from main"),
            (FakeRunner(behind=True), "differs from origin/main"),
            (FakeRunner(tag_exists=True), "already exists"),
        ],
    )
    def test_refuses_unless_it_is_safe(self, repo, runner, message):
        before = snapshot(repo)

        with pytest.raises(rs.ReleaseError, match=message):
            rs.release(["patch", "--yes"], runner)

        assert snapshot(repo) == before
        assert not runner.ran("git", "push")
