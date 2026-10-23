#!/usr/bin/env bash
# Export libs/shared as it is at a git tag into .build/<tag>/libs/shared, so a service can be
# built and run against that release: `make up AUTH_SHARED=shared/v0.2.0` (see the Makefile).
#
# Usage: scripts/export-shared.sh <tag>
set -euo pipefail

tag="${1:?usage: scripts/export-shared.sh <tag>}"
cd "$(git rev-parse --show-toplevel)"

if ! git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  echo "export-shared: no tag $tag here (try: git fetch --tags)" >&2
  exit 1
fi
if ! git cat-file -e "$tag:libs/shared/pyproject.toml" 2>/dev/null; then
  echo "export-shared: $tag has no libs/shared (tags before the rename used libs/ca_authlib)" >&2
  exit 1
fi

dest=".build/$tag"
commit="$(git rev-parse "$tag^{commit}")"
# Already exported at this commit: keep it. Deleting and re-extracting would pull the directory
# out from under a running container that bind-mounts it.
if [ "$(cat "$dest/.commit" 2>/dev/null)" = "$commit" ]; then
  echo "export-shared: $tag already at $dest/libs/shared"
  exit 0
fi
rm -rf "$dest"
mkdir -p "$dest"
git archive "$tag" libs/shared | tar -x -C "$dest"
echo "$commit" >"$dest/.commit"

# The image installs third-party packages from this checkout's uv.lock. A release that needs a
# different set would build, then fail at import, so say so now.
uv run --quiet python - "$dest/libs/shared/pyproject.toml" <<'PY'
import sys, tomllib

def wanted(path):
    project = tomllib.load(open(path, "rb"))["project"]
    extras = project.get("optional-dependencies", {})
    return sorted(project.get("dependencies", [])), {k: sorted(v) for k, v in extras.items()}

if wanted(sys.argv[1]) != wanted("libs/shared/pyproject.toml"):
    print(f"export-shared: warning: {sys.argv[1]} declares different dependencies than "
          "libs/shared; the image installs the ones in uv.lock", file=sys.stderr)
PY
echo "export-shared: $tag -> $dest/libs/shared"
