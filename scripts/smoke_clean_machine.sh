#!/bin/zsh
# Clean-machine smoke (W9, week-4 gate): a pristine container installs the
# wheel and runs the FULL wedge loop across both product halves —
#   the reading:  read (walking) -> epitaph -> receipts verify ->
#                 restore (declared) -> strict passes
#   the gate:     forget (grave with proof) -> guard locks it ->
#                 undeclared return FAILS with kill history ->
#                 sanctioned restore -> check passes
#
#   PRE-publish:  zsh scripts/smoke_clean_machine.sh          (local wheel)
#   POST-publish: zsh scripts/smoke_clean_machine.sh --pypi   (the real path:
#                 what a stranger types)
set -euo pipefail
HERE="${0:A:h:h}"
MODE="${1:-wheel}"

if [ "$MODE" != "--pypi" ]; then
  ( cd "$HERE" && python3 -m build --wheel >/dev/null 2>&1 ) \
    || { echo "wheel build failed (pip install build)"; exit 1; }
  WHEEL="$(ls -t "$HERE"/dist/sagrada_linter-0.2.0-*.whl | head -1)"
  INSTALL="pip install --quiet /w/$(basename "$WHEEL")"
  VOL=(-v "$WHEEL:/w/$(basename "$WHEEL"):ro")
else
  INSTALL="pip install --quiet sagrada-linter==0.2.0"
  VOL=()
fi

INNER_SCRIPT="$(mktemp)"
cat > "$INNER_SCRIPT" <<'INNER'
set -euo pipefail
step() { echo "== $1 =="; }
die() { echo "SMOKE FAILED: $1"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update >/dev/null && apt-get -qq install -y git >/dev/null
__INSTALL__
git config --global user.email t@t; git config --global user.name t
git config --global init.defaultBranch main
mkdir /r && cd /r && git init -q
A="- deploy-gate — run migrations manually before deploy"
B="- old-audit — require checksum audits before release"
printf '%s\n' "# Rules" "$A" "$B" > CLAUDE.md
git add .; git commit -qm born
printf '%s\n' "# Rules" "$B" > CLAUDE.md
git add .; git commit -qm "killed: staging incident"
printf '%s\n' "# Rules" "$A" "$B" > CLAUDE.md
git add .; git commit -qm "merge old branch"

step "read catches the walking rule, drops the epitaph, strict says 1"
sagrada-linter read . --no-pace --html /r/epitaphs.html --receipt \
  | grep -q "WALKING" || die "read did not report WALKING"
sagrada-linter read . --no-pace --strict >/dev/null && die "strict should exit 1" || true
test -f /r/epitaphs.html || die "epitaph file missing"
if grep -qi "<script" /r/epitaphs.html; then die "epitaph must be script-free"; fi
echo OK-read

step "receipts verify (offline property pinned in the suite)"
sagrada-linter verify /r/.sagrada/receipts/*.er1.json >/dev/null || die verify
echo OK-verify

step "declared restoration: strict passes"
sagrada-linter restore CLAUDE.md 2 --reason "needed for Q3" >/dev/null || die restore
git add .; git commit -qm "declared restoration"
sagrada-linter read . --no-pace --strict >/dev/null || die "strict should acquit"
echo OK-restore

step "forget digs a grave with proof"
sagrada-linter forget CLAUDE.md 3 --reason "audits retired" >/dev/null || die forget
if grep -q "old-audit" CLAUDE.md; then die "line should be gone"; fi
test -s .sagrada/tombstones.jsonl || die tombstone
git add .; git commit -qm "forgotten with proof"
echo OK-forget

step "guard locks the grave; clean check passes"
sagrada-linter guard --repo . >/dev/null || die "guard install"
grep -q "old_audit" .crux/lock.json || die "grave not locked"
sagrada-linter guard --repo . --check >/dev/null || die "clean check"
echo OK-guard

step "undeclared resurrection FAILS with the kill history"
printf '%s\n' "$B" >> CLAUDE.md
if out="$(sagrada-linter guard --repo . --check)"; then die "check should fail"; fi
echo "$out" | grep -q "killed at" || die "kill history missing"
echo OK-gate-fails

step "the sanctioned path passes with the paperwork counted"
line=$(grep -n "old-audit" CLAUDE.md | cut -d: -f1)
sagrada-linter restore CLAUDE.md "$line" --reason "audits back for SOC2" >/dev/null || die "restore B"
sagrada-linter guard --repo . --check | grep -q "sanctioned" || die "sanction not counted"
echo OK-sanction
echo "CLEAN-MACHINE SMOKE: ALL OK"
INNER

sed -i '' "s|__INSTALL__|$INSTALL|" "$INNER_SCRIPT"
docker run --rm "${VOL[@]}" -v "$INNER_SCRIPT:/smoke.sh:ro" \
  python:3.11-slim /bin/bash /smoke.sh
