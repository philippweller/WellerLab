#!/usr/bin/env bash
#
# upload-pypi.sh — ONLY uploads the already-built WellerLab wheels to PyPI.
#
#   - Does NOT build (no setuptools noise).
#   - Uploads every wheel/sdist already present in dist-pypi/.
#   - Prints a clear, short result: success (View at) or the HTTP error line.
#
# Usage:
#   export TWINE_USERNAME='__token__'
#   export TWINE_PASSWORD='pypi-...'
#   ./upload-pypi.sh
#
set -u

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
  echo "!! TWINE credentials not set in this shell. Run:" >&2
  echo "   export TWINE_USERNAME='__token__'" >&2
  echo "   export TWINE_PASSWORD='pypi-<your-token>'" >&2
  exit 1
fi

ORANGEPY="${ORANGEPY:-/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"

FILES=( dist-pypi/*.whl dist-pypi/*.tar.gz )

missing=0
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { echo "fehlt: $f" >&2; missing=1; }
done
[[ $missing -eq 0 ]] || { echo "!! dist-pypi/ unvollständig — erst bauen (publish-pypi.sh) oder Dateien prüfen." >&2; exit 1; }

echo "==> Uploading $((${#FILES[@]})) artefacts to PyPI"
"$ORANGEPY" -m twine upload "${FILES[@]}"