#!/usr/bin/env bash
# run-all.sh — driver that runs 00 → 03 in sequence with confirmation
# gates between each step. Each gate lets you abort cleanly between
# steps if the previous one revealed a problem.

source "$(dirname "$0")/lib.sh"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
START="$(date +%s)"

step "Sequence: 00 → 01 → 02 → 03"
log_to "run-all"
print_state

"$SCRIPT_DIR/00-preflight.sh"
confirm "Pre-flight passed. Continue to MSSQL backup?"

"$SCRIPT_DIR/01-mssql.sh"
confirm "MSSQL backup done. Continue to Synapse parquet?"

"$SCRIPT_DIR/02-synapse.sh"
confirm "Synapse backup done. Continue to Key Vault?"

"$SCRIPT_DIR/03-keyvault.sh"

step "Generate final MANIFEST.md"
{
  echo "# Legacy Backup Manifest"
  echo
  echo "- Captured: $(ts)"
  echo "- Operator: $(whoami)@$(hostname)"
  echo "- Subscription: $LEGACY_SUB_ID"
  echo "- AKS cluster: $LEGACY_AKS"
  echo "- Storage account: $LEGACY_STORAGE_ACCT"
  echo
  echo "## mssql/"
  ls -lh "$BACKUP_DIR/mssql/" 2>/dev/null | tail -n +2
  echo
  echo "## synapse/"
  du -sh "$BACKUP_DIR/synapse/"* 2>/dev/null
  echo
  echo "## keyvault.age"
  ls -lh "$BACKUP_DIR/keyvault.age" 2>/dev/null
  echo
  echo "## Verify reports"
  echo
  echo "### MSSQL smoke-restore (01-mssql.sh §1.4)"
  cat "$BACKUP_DIR/mssql/verify.txt" 2>/dev/null || echo "(missing)"
  echo
  echo "### Synapse parquet read (02-synapse.sh §2.3)"
  cat "$BACKUP_DIR/synapse/verify.txt" 2>/dev/null || echo "(missing)"
} > "$BACKUP_DIR/MANIFEST.md"

ok "Manifest: $BACKUP_DIR/MANIFEST.md"

END="$(date +%s)"
DUR=$((END - START))
echo
ok "ALL DONE in $((DUR/60))m $((DUR%60))s"
echo
echo "Total backup size:"
du -sh "$BACKUP_DIR"
echo
echo "Next steps:"
echo "  1. Upload \$BACKUP_DIR to off-site storage (B2 / R2 / Glacier — see BACKUP_RUNBOOK.md §8)"
echo "  2. Store the age passphrase in your password manager"
echo "  3. Delete the local copy AFTER off-site upload confirmed"
echo "  4. Proceed to AZURE_SHUTDOWN_AUDIT.md §4 (Azure shutdown sequence)"
