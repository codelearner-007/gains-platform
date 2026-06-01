# Shared helpers. Sourced by every step script. Not executable directly.

set -euo pipefail

# ── Load .env from script dir ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "ERROR: $SCRIPT_DIR/.env not found. Copy .env.example to .env and fill in values." >&2
  exit 2
fi
set -a; source "$SCRIPT_DIR/.env"; set +a

# ── Derived paths ─────────────────────────────────────────────────────────
: "${BACKUP_ROOT:=$HOME/Desktop/PS_P}"
BACKUP_DIR="${BACKUP_DIR:-$BACKUP_ROOT/legacy-backup-$(date +%Y%m%d)}"
LOG_DIR="$BACKUP_DIR/logs"
mkdir -p "$LOG_DIR" "$BACKUP_DIR"/{mssql,synapse,keyvault}

# ── Logging ───────────────────────────────────────────────────────────────
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] $*"; }
ok()  { echo "[$(ts)] ✔ $*"; }
warn(){ echo "[$(ts)] ⚠ $*" >&2; }
die() { echo "[$(ts)] ✗ $*" >&2; exit 1; }
step(){ echo; echo "=============================================="; echo "$*"; echo "=============================================="; }

# Tee a step's stdout+stderr into a log file
log_to() {
  local name="$1"
  local logfile="$LOG_DIR/${name}-$(date +%H%M%S).log"
  log "→ logging to $logfile"
  exec > >(tee -a "$logfile") 2>&1
}

# ── Tool checks ───────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }

require_tool() {
  local tool="$1" install_hint="${2:-(no install hint)}"
  if ! have "$tool"; then
    die "Missing tool: $tool. Install: $install_hint"
  fi
}

require_env() {
  local name="$1"
  local val="${!name:-}"
  if [[ -z "$val" || "$val" == "REPLACE_ME" ]]; then
    die "Missing env var: $name (edit .env)"
  fi
}

# ── Confirm gate ──────────────────────────────────────────────────────────
confirm() {
  local prompt="$1"
  read -r -p "$prompt [y/N] " ans
  [[ "${ans:-}" =~ ^[Yy]$ ]] || die "Aborted by user."
}

# ── Friendly state summary for reuse across scripts ───────────────────────
print_state() {
  log "BACKUP_DIR = $BACKUP_DIR"
  log "LEGACY_SUB_ID = $LEGACY_SUB_ID"
  log "LEGACY_AKS = $LEGACY_AKS"
  log "MSSQL = $MSSQL_NAMESPACE/$MSSQL_POD"
}
