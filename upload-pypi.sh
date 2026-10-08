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

ORANGEPY="${ORANGEPY:-/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"

# Credentials from TWINE_* env vars OR a readable ~/.pypirc [pypi] section.
if [[ -z "${TWINE_USERNAME:-}" || -z "${TWINE_PASSWORD:-}" ]]; then
  if [[ -r "$HOME/.pypirc" ]] && "$ORANGEPY" - "$HOME/.pypirc" <<'PY'
import configparser, sys
c = configparser.ConfigParser(); c.read(sys.argv[1])
sys.exit(0 if c.has_option("pypi", "password") else 1)
PY
  then
    :  # ~/.pypirc provides the token; twine reads it itself
  else
    echo "!! No PyPI credentials. Either export them:" >&2
    echo "   export TWINE_USERNAME='__token__'" >&2
    echo "   export TWINE_PASSWORD='pypi-<your-token>'" >&2
    echo "   ...or add a [pypi] password to ~/.pypirc (chmod 600)." >&2
    exit 1
  fi
fi

FILES=( dist-pypi/*.whl dist-pypi/*.tar.gz )

missing=0
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || { echo "fehlt: $f" >&2; missing=1; }
done
[[ $missing -eq 0 ]] || { echo "!! dist-pypi/ unvollständig — erst bauen (publish-pypi.sh) oder Dateien prüfen." >&2; exit 1; }

echo "==> Uploading $((${#FILES[@]})) artefacts to PyPI (skipping already-uploaded)"
"$ORANGEPY" -m twine upload --skip-existing "${FILES[@]}"