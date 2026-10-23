#!/usr/bin/env python3
"""Release the shared library: bump its version, check it, commit, tag shared/vX.Y.Z, push.

    make release-shared BUMP=patch            # or minor, major, or an explicit X.Y.Z
    make release-shared ARGS=--tag-current    # tag the current version without bumping
    uv run python scripts/release_shared.py minor --dry-run

Refuses unless the tree is clean, you are on main and main matches origin/main. Writes the
new version to libs/shared, widens a service's `shared` range when it no longer admits the new
version (inside this workspace both services must follow, or `uv lock` fails), relocks, runs
the library's tests, shows what it is about to do and asks before committing, tagging and
pushing. Other projects then depend on the tag (see libs/shared/README.md).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_PYPROJECT = ROOT / "libs/shared/pyproject.toml"
LIB_INIT = ROOT / "libs/shared/src/shared/__init__.py"
LOCKFILE = ROOT / "uv.lock"
REMOTE = "origin"
BRANCH = "main"
TAG_PREFIX = "shared/v"

Version = tuple[int, int, int]


class ReleaseError(Exception):
    """A check failed; nothing was committed, tagged or pushed."""


# --- versions ------------------------------------------------------------------------------


def parse_version(text: str) -> Version:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text.strip())
    if not match:
        raise ReleaseError(f"not a version (expected X.Y.Z): {text!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


def next_version(current: Version, bump: str) -> Version:
    major, minor, patch = current
    if bump == "major":
        new = (major + 1, 0, 0)
    elif bump == "minor":
        new = (major, minor + 1, 0)
    elif bump == "patch":
        new = (major, minor, patch + 1)
    else:
        new = parse_version(bump)
    if new <= current:
        raise ReleaseError(
            f"{format_version(new)} is not newer than the current {format_version(current)}"
        )
    return new


def read_version(pyproject_text: str) -> Version:
    match = re.search(r'^version = "([^"]+)"', pyproject_text, re.MULTILINE)
    if not match:
        raise ReleaseError("no version in libs/shared/pyproject.toml")
    return parse_version(match.group(1))


def set_pyproject_version(text: str, version: Version) -> str:
    return re.sub(
        r'^version = "[^"]+"',
        f'version = "{format_version(version)}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )


def set_init_version(text: str, version: Version) -> str:
    return re.sub(
        r'^__version__ = "[^"]+"',
        f'__version__ = "{format_version(version)}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )


# --- service ranges --------------------------------------------------------------------------

# A service's dependency, e.g. "shared[drf,wp]>=0.2,<0.3".
REQUIREMENT = re.compile(
    r'"shared(?P<extras>\[[^\]]*\])?>=(?P<low>\d+(?:\.\d+){0,2}),<(?P<high>\d+(?:\.\d+){0,2})"'
)


def _as_version(text: str) -> Version:
    parts = [int(p) for p in text.split(".")] + [0, 0]
    return parts[0], parts[1], parts[2]


def compatible_range(version: Version) -> tuple[str, str]:
    """The semver range a release belongs to: ^0.3.x is >=0.3,<0.4; ^1.x is >=1.0,<2.0."""
    major, minor, _ = version
    if major == 0:
        return f"0.{minor}", f"0.{minor + 1}"
    return f"{major}.0", f"{major + 1}.0"


def widen_service_range(text: str, version: Version) -> tuple[str, bool]:
    """Return the pyproject text with its `shared` range moved to admit `version` (only when
    the current range does not), and whether it changed."""
    match = REQUIREMENT.search(text)
    if not match:
        raise ReleaseError("a service pyproject.toml has no shared>=A,<B dependency")
    if _as_version(match["low"]) <= version < _as_version(match["high"]):
        return text, False
    low, high = compatible_range(version)
    replacement = f'"shared{match["extras"] or ""}>={low},<{high}"'
    return text[: match.start()] + replacement + text[match.end() :], True


# --- the release -------------------------------------------------------------------------------


class Runner:
    """Runs commands in the repository. Tests replace it."""

    def run(self, *cmd: str, capture: bool = False) -> str:
        result = subprocess.run(  # noqa: S603 (fixed commands, no shell)
            cmd, cwd=ROOT, check=False, text=True, capture_output=capture
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip() if capture else ""
            raise ReleaseError(f"command failed: {' '.join(cmd)}\n{detail}".rstrip())
        return result.stdout if capture else ""


def preflight(runner: Runner, tag: str) -> None:
    if runner.run("git", "status", "--porcelain", capture=True).strip():
        raise ReleaseError("the working tree has changes; commit or stash them first")
    branch = runner.run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True).strip()
    if branch != BRANCH:
        raise ReleaseError(f"releases are cut from {BRANCH}; you are on {branch}")
    runner.run("git", "fetch", "--quiet", REMOTE, BRANCH, "--tags")
    head = runner.run("git", "rev-parse", "HEAD", capture=True).strip()
    upstream = runner.run("git", "rev-parse", f"{REMOTE}/{BRANCH}", capture=True).strip()
    if head != upstream:
        raise ReleaseError(f"{BRANCH} differs from {REMOTE}/{BRANCH}; pull or push first")
    if runner.run("git", "tag", "--list", tag, capture=True).strip():
        raise ReleaseError(f"tag {tag} already exists")


def release(argv: list[str], runner: Runner, ask=input) -> str:
    """Run a release. Returns the tag. Raises ReleaseError (with every file restored) if
    anything fails or the release is declined."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bump", nargs="?", help="patch, minor, major or X.Y.Z")
    parser.add_argument("--tag-current", action="store_true", help="tag the current version")
    parser.add_argument("--dry-run", action="store_true", help="check and show, change nothing")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--build", action="store_true", help="also build the wheel into dist/")
    args = parser.parse_args(argv)
    if bool(args.bump) == args.tag_current:
        parser.error("give a bump (patch, minor, major or X.Y.Z) or --tag-current, not both")

    current = read_version(LIB_PYPROJECT.read_text())
    new = current if args.tag_current else next_version(current, args.bump)
    tag = f"{TAG_PREFIX}{format_version(new)}"
    preflight(runner, tag)

    services = sorted((ROOT / "services").glob("*/pyproject.toml"))
    originals = {path: path.read_text() for path in [LIB_PYPROJECT, LIB_INIT, LOCKFILE, *services]}

    def restore() -> None:
        for path, text in originals.items():
            path.write_text(text)

    try:
        notes = []
        if not args.tag_current:
            LIB_PYPROJECT.write_text(set_pyproject_version(originals[LIB_PYPROJECT], new))
            LIB_INIT.write_text(set_init_version(originals[LIB_INIT], new))
            for path in services:
                text, changed = widen_service_range(originals[path], new)
                if changed:
                    path.write_text(text)
                    notes.append(f"{path.relative_to(ROOT)}: shared range moved to admit {tag}")
            runner.run("uv", "lock", "--quiet")
        runner.run(
            "uv", "run", "--package", "shared", "--group", "test", "pytest", "-q", "libs/shared"
        )

        changed_files = [
            line[3:]
            for line in runner.run("git", "status", "--porcelain", capture=True).splitlines()
        ]
        print(f"\nshared {format_version(current)} -> {format_version(new)}")
        print(f"  tag:     {tag}")
        print(f"  push:    {REMOTE} {BRANCH} {tag}")
        print(f"  changes: {', '.join(changed_files) or 'none (tagging the current commit)'}")
        for note in notes:
            print(f"  note:    {note}")

        if args.dry_run:
            restore()
            print("\nDry run: files restored; nothing was committed, tagged or pushed.")
            return tag
        if not args.yes and ask(f"\nRelease {tag} and push it? [y/N] ").strip().lower() != "y":
            raise ReleaseError("not released")

        if changed_files:
            runner.run("git", "add", *changed_files)
            runner.run("git", "commit", "--quiet", "-m", f"shared {format_version(new)}")
    except BaseException:
        restore()
        raise

    runner.run("git", "tag", "-a", tag, "-m", f"shared {format_version(new)}")
    runner.run("git", "push", "--atomic", REMOTE, BRANCH, tag)
    if args.build:
        runner.run("uv", "build", "--package", "shared")
    print(f"\nReleased {tag}. Another project can now depend on it, e.g.")
    print(
        f'  shared = {{ git = "ssh://git@github.com/michaelwayman/ca-challenge.git", '
        f'subdirectory = "libs/shared", tag = "{tag}" }}'
    )
    return tag


def main() -> int:
    try:
        release(sys.argv[1:], Runner())
    except ReleaseError as exc:
        print(f"release-shared: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
