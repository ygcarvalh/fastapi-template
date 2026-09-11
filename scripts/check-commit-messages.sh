#!/usr/bin/env bash
set -euo pipefail

types="feat|fix|docs|style|refactor|test|chore|perf"
pattern="^($types)(\([a-z0-9._/-]+\))?!?: .+"

explain() {
    echo >&2
    echo "Expected '<type>: <subject>' with type one of: ${types//|/ }" >&2
}

check_message_file() {
    local subject
    subject="$(grep -m1 -v '^#' "$1" || true)"
    if [[ ! $subject =~ $pattern ]]; then
        echo "Commit subject does not follow Conventional Commits:" >&2
        echo "  $subject" >&2
        explain
        exit 1
    fi
}

check_range() {
    local range="$1"
    local offenders=()
    while IFS=$'\t' read -r sha subject; do
        [[ -n $sha ]] || continue
        [[ $subject =~ $pattern ]] || offenders+=("${sha:0:8} $subject")
    done < <(git log --no-merges --format='%H%x09%s' "$range")

    if ((${#offenders[@]})); then
        echo "Commit subjects that do not follow Conventional Commits:" >&2
        printf '  %s\n' "${offenders[@]}" >&2
        explain
        exit 1
    fi
    echo "Every commit subject in $range follows Conventional Commits."
}

# A file argument is what git hands a commit-msg hook; anything else is a range.
if [[ -f ${1:-} ]]; then
    check_message_file "$1"
else
    check_range "${1:-origin/main..HEAD}"
fi
