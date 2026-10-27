#!/usr/bin/env bash
# Disposable GitHub-hosted runner only.
set -euo pipefail
snapshot() {
  printf '\n=== disk stage=%s UTC=%s ===\n' "$1" "$(date -u +%FT%TZ)"
  df -hT /
  df -B1 --output=source,avail /
}
case "${1:-}" in
  setup)
    [[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted && ${RUNNER_OS:-} == Linux ]]
    for p in /usr/share/dotnet /usr/local/lib/android /opt/ghc /usr/local/.ghcup \
      /usr/share/swift /usr/local/share/powershell /usr/local/share/boost \
      /opt/hostedtoolcache/CodeQL /opt/hostedtoolcache/Ruby; do
      if [[ -d "$p" && ! -L "$p" ]]; then
        sudo rm -rf --one-file-system -- "$p"
      fi
    done
    sudo apt-get clean
    export WORK="${RUNNER_TEMP}/r4-build"
    [[ ! -e "$WORK" ]]
    mkdir -p "$WORK/evidence"
    printf 'WORK=%s\n' "$WORK" >> "$GITHUB_ENV"
    snapshot after-sdk-cleanup | tee "$WORK/evidence/disk.txt"
    ;;
  snapshot)
    snapshot "${2:?stage required}" | tee -a "$WORK/evidence/disk.txt"
    ;;
  *) exit 2 ;;
esac
