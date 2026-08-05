#!/usr/bin/env bash
set -euo pipefail

range="${1:-origin/main..HEAD}"

types="feat|fix|docs|style|refactor|test|chore|perf"
pattern="^($types)(\([a-z0-9._/-]+\))?!?: .+"

offenders=()
while IFS=$'\t' read -r sha subject; do
    [[ -n $sha ]] || continue
    [[ $subject =~ $pattern ]] || offenders+=("${sha:0:8} $subject")
done < <(git log --no-merges --format='%H%x09%s' "$range")

if ((${#offenders[@]})); then
    echo "Commit subjects that do not follow Conventional Commits:" >&2
    printf '  %s\n' "${offenders[@]}" >&2
    echo >&2
    echo "Expected '<type>: <subject>' with type one of: ${types//|/ }" >&2
    exit 1
fi

echo "Every commit subject in $range follows Conventional Commits."
