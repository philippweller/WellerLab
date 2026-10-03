#!/usr/bin/env bash
#
# upload-pypi.sh — ONLY uploads the already-built WellerLab wheels to PyPI.
#
#   - Does NOT build (no setuptools noise).
#   - Uploads the 6 artefacts already present in dist-pypi/.
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

FILES=( dist-pypi/orangenmr-0.1.0-py3-none-any.whl
        dist-pypi/orangenmr-0.1.0.tar.gz
        dist-pypi/orangepca-0.1.1-py3-none-any.whl
        dist-pypi/orangepca-0.1.1.tar.gz
        dist-pypi/orangeplsda-0.1.0-py3-none-any.whl
        dist-pypi/orangeplsda-0.1.0.tar.gz )

missing=0
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { echo "fehlt: $f" >&2; missing=1; }
done
[[ $missing -eq 0 ]] || { echo "!! dist-pypi/ unvollständig — erst bauen (publish-pypi.sh) oder Dateien prüfen." >&2; exit 1; }

echo "==> Uploading $((${#FILES[@]})) artefacts to PyPI"
"$ORANGEPY" -m twine upload "${FILES[@]}"