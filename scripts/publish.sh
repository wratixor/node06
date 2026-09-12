#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not inside a Git repository." >&2
  exit 1
fi

python3 build.py

echo
echo "Build OK. Git status:"
git status --short

echo
if [[ $# -gt 0 ]]; then
  message="$*"
else
  read -r -p "Commit message: " message
fi

if [[ -z "${message// }" ]]; then
  echo "Commit message cannot be empty." >&2
  exit 1
fi

git add -A

if git diff --cached --quiet; then
  echo "Nothing to commit."
  exit 0
fi

git commit -m "$message"
git push

echo
echo "Pushed. GitHub Actions will build and deploy NODE06 to Neocities."
