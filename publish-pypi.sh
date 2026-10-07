#!/usr/bin/env bash
#
# publish-pypi.sh — build + publish the WellerLab Orange3 add-ons to PyPI.
#
# Usage:
#   ./publish-pypi.sh [--test] [pkg1 pkg2 ...]
#
#   --test   upload to TestPyPI instead of real PyPI
#   pkgs     which packages; default = all four (plsda nmr pca metabo)
#
# Requirements:
#   - run with Orange's own python so deps are satisfied:
#       ORANGEPY=/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
#   - a PyPI API token. Export it, or set in ~/.pypirc:
#       export TWINE_USERNAME=__token__
#       export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmc...your-token
#
# After publishing, group members can install inside Orange via
#   Orange → Options → Add-ons → Add add-on by name → type the package name
#   (orangeplsda / orangenmr / orangepca / orangemetabo)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$SCRIPT_DIR"

ORANGEPY="${ORANGEPY:-/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"

# bash 3.2 (macOS default) has no associative arrays -> use a case map.
subdir_of() {
  case "$1" in
    plsda) echo orange-plsda-addon ;;
    nmr)   echo orange-nmr-addon ;;
    pca)   echo orange-pca-addon ;;
    metabo) echo orange-metabo-addon ;;
    *)     echo "" ;;
  esac
}

TEST=0
if [[ "${1:-}" == "--test" ]]; then TEST=1; shift; fi

PKGS=()
if [[ $# -gt 0 ]]; then
  for p in "$@"; do
    [[ -n "$(subdir_of "$p")" ]] || { echo "unknown pkg: $p (use plsda|nmr|pca|metabo)" >&2; exit 2; }
    PKGS+=("$p")
  done
else
  PKGS=(plsda nmr pca metabo)
fi

OUT="$REPO/dist-pypi"
mkdir -p "$OUT"

echo "==> Ensuring build + twine present (with Orange's python)"
"$ORANGEPY" -m pip install --no-user --upgrade build twine >/dev/null

for p in "${PKGS[@]}"; do
  d="$REPO/$(subdir_of "$p")"
  echo
  echo "==> Building $p ($d)"
  # Build quietly: keep setuptools' tall log only on failure; on success show
  # just the "Successfully built" line. Still aborts on a real build error.
  buildlog="$(mktemp)"
  if ! "$ORANGEPY" -m build --wheel --sdist --outdir "$OUT" "$d" >"$buildlog" 2>&1; then
    echo "BUILD FAILED for $p:" >&2
    cat "$buildlog" >&2
    rm -f "$buildlog"
    exit 1
  fi
  grep -E "Successfully built" "$buildlog" || true
  rm -f "$buildlog"
done

echo
echo "==> Artefacts in $OUT:"
ls -1 "$OUT"/*.whl "$OUT"/*.tar.gz

if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
  echo
  echo "!! No TWINE creds set. Publish with:"
  echo "   export TWINE_USERNAME=__token__"
  echo "   export TWINE_PASSWORD=your-pypi-api-token"
  if [[ $TEST -eq 1 ]]; then
    echo "   twine upload --repository testpypi $OUT/*.whl $OUT/*.tar.gz"
  else
    echo "   twine upload \"$OUT\"/*.whl \"$OUT\"/*.tar.gz"
  fi
  exit 0
fi

if [[ $TEST -eq 1 ]]; then
  echo "==> Publishing to TestPyPI"
  "$ORANGEPY" -m twine upload --repository testpypi "$OUT"/*.whl "$OUT"/*.tar.gz
else
  echo "==> Publishing to PyPI"
  "$ORANGEPY" -m twine upload "$OUT"/*.whl "$OUT"/*.tar.gz
fi

echo "==> Done. Point in the installer/READMEs at PyPI; verify at pypi.org/project/<name>/"