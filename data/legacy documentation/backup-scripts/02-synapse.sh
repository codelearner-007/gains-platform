#!/usr/bin/env bash
# 02-synapse.sh — selective ADLS Gen2 backup focused on what's actually
# needed to replay the full assessment pipeline in the new platform.
#
# Backs up:
#   A. Raw CSVs in pre_landing/Schoology/{2024-25,2025-26}     ← all assessment data
#   B. 8 canonical cubes in dev/stage3/Published/schoology/v0.1 ← processed ground-truth
#
# Skips: Test/, success markers, _delta_log/, _temporary/,
#        __HIVE_DEFAULT_PARTITION__, all duplicate/orphan cube variants.

source "$(dirname "$0")/lib.sh"
log_to "02-synapse"

step "2.1  Generate read-only SAS (24h)"
if date -u -v+24H +%s >/dev/null 2>&1; then
  EXPIRY="$(date -u -v+24H +%Y-%m-%dT%H:%MZ)"
else
  EXPIRY="$(date -u -d '+24 hours' +%Y-%m-%dT%H:%MZ)"
fi
SAS="$(az storage account generate-sas \
  --account-name "$LEGACY_STORAGE_ACCT" \
  --services bfqt --resource-types sco \
  --permissions rl \
  --expiry "$EXPIRY" \
  --https-only -o tsv)"
[[ -n "$SAS" ]] || die "Failed to generate SAS"
ok "SAS valid until $EXPIRY"

ACCT_URL="https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea"

# What we exclude on every azcopy: Delta lake bookkeeping + Spark scratch +
# Hive null partitions. None of these are useful for replay.
EXCLUDE_PATH="_delta_log;_temporary;__HIVE_DEFAULT_PARTITION__"

# ── A) Raw CSV pre_landing — drives the replay ────────────────────────────
step "2.2  Raw CSVs — pre_landing/Schoology"
PL_DIR="$BACKUP_DIR/synapse/pre_landing/Schoology"
mkdir -p "$PL_DIR"

# Only academic-year subdirs (skip the Test/ trash + success markers at root)
for year in 2024-25 2025-26; do
  if [[ -d "$PL_DIR/$year" ]] && find "$PL_DIR/$year" -name '*.csv' -print -quit 2>/dev/null | grep -q .; then
    log "↷ pre_landing/$year already has CSVs locally, skipping (delete folder to redo)"
    continue
  fi
  log "▶ pre_landing/Schoology/$year/  (CSV + Schoology export bundle)"
  azcopy copy \
    "${ACCT_URL}/pre_landing/Schoology/${year}?${SAS}" \
    "$PL_DIR/" \
    --recursive \
    --include-pattern "*.csv;*.json;*.html;*.zip" \
    --log-level=INFO \
    --output-type=text 2>&1 \
    | tee -a "$LOG_DIR/azcopy-pre_landing-${year}.log" \
    | grep -E "^(Number of|Final Job|Job |Elapsed|Total)" || true
  ok "pre_landing/$year copied"
done

# ── B) Canonical cubes — parquet only ─────────────────────────────────────
step "2.3  Stage3 canonical cubes (parquet only)"
CUBES_DIR="$BACKUP_DIR/synapse/stage3_cubes"
mkdir -p "$CUBES_DIR"

# The 8 canonical published cubes — names verified against
# Schoology_py.ipynb (cube_Build function) and 04_oea.md §5.
CANONICAL_CUBES=(
  Cube_Grade_Summary
  Cube_School_Summary
  Cube_Standard_Summary
  Cube_Question_Summary
  Cube_Question_Summary_Overall
  Cube_QuestionIncorrectChoice_Summary
  Cube_User_Summary
  Cube_OverallPerformance_Summary
)

for cube in "${CANONICAL_CUBES[@]}"; do
  local_path="$CUBES_DIR/$cube"
  if [[ -d "$local_path" ]] && find "$local_path" -name '*.parquet' -print -quit 2>/dev/null | grep -q .; then
    log "↷ $cube already has parquet locally, skipping"
    continue
  fi

  log "▶ stage3/.../v0.1/$cube/"
  azcopy copy \
    "${ACCT_URL}/dev/stage3/Published/schoology/v0.1/${cube}?${SAS}" \
    "$CUBES_DIR/" \
    --recursive \
    --include-pattern "*.parquet" \
    --exclude-path "$EXCLUDE_PATH" \
    --log-level=INFO \
    --output-type=text 2>&1 \
    | tee -a "$LOG_DIR/azcopy-cube-${cube}.log" \
    | grep -E "^(Number of|Final Job|Job |Elapsed|Total)" || true
  ok "$cube copied"
done

# ── C) Stage1 canonical Delta — typed raw (regenerable but cheap to grab) ─
# These are the 6 typed Delta tables the notebook builds from pre_landing CSVs.
# Mostly there to short-cut the replay if anyone wants to skip stage1 build.
step "2.4  Stage1 canonical Delta tables (parquet only)"
S1_DIR="$BACKUP_DIR/synapse/stage1_transactional"
mkdir -p "$S1_DIR"

STAGE1_TABLES=(question_data roles standards student_submissions submission_summary users)

for tbl in "${STAGE1_TABLES[@]}"; do
  local_path="$S1_DIR/$tbl"
  if [[ -d "$local_path" ]] && find "$local_path" -name '*.parquet' -print -quit 2>/dev/null | grep -q .; then
    log "↷ stage1/$tbl already has parquet locally, skipping"
    continue
  fi
  log "▶ stage1/Transactional/schoology/v0.1/$tbl/"
  azcopy copy \
    "${ACCT_URL}/dev/stage1/Transactional/schoology/v0.1/${tbl}?${SAS}" \
    "$S1_DIR/" \
    --recursive \
    --include-pattern "*.parquet" \
    --exclude-path "$EXCLUDE_PATH" \
    --log-level=INFO \
    --output-type=text 2>&1 \
    | tee -a "$LOG_DIR/azcopy-stage1-${tbl}.log" \
    | grep -E "^(Number of|Final Job|Job |Elapsed|Total)" || true
  ok "stage1/$tbl copied"
done

# ── D) Verify a parquet + a CSV are readable ──────────────────────────────
step "2.5  Verify a parquet + a CSV from the bundle"
PY="$(command -v python3 || command -v python)"
[[ -n "$PY" ]] || die "Need python3 to verify parquet"

if ! "$PY" -c "import pyarrow" 2>/dev/null; then
  log "Installing pyarrow into a throwaway venv"
  VENV="$BACKUP_DIR/.verify-venv"
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet pyarrow
  PY="$VENV/bin/python"
fi

VERIFY="$BACKUP_DIR/synapse/verify.txt"
: > "$VERIFY"

# Sample parquet from each cube
for cube in "${CANONICAL_CUBES[@]}"; do
  sample="$(find "$CUBES_DIR/$cube" -name '*.parquet' 2>/dev/null | head -1)"
  if [[ -z "$sample" ]]; then
    echo "$cube: NO PARQUET" >> "$VERIFY"
    warn "$cube: no parquet found"
    continue
  fi
  out="$("$PY" - <<PYEOF
import pyarrow.parquet as pq
t = pq.read_table("$sample")
print(f"{t.num_rows} rows, {t.num_columns} cols, cols={list(t.column_names)[:5]}")
PYEOF
)"
  echo "$cube: $(basename "$sample") → $out" >> "$VERIFY"
  ok "$cube → $out"
done

# Sample CSV from pre_landing
csv_sample="$(find "$PL_DIR" -name '*.csv' 2>/dev/null | head -1)"
if [[ -n "$csv_sample" ]]; then
  rows=$(wc -l < "$csv_sample")
  echo "pre_landing sample: $(basename "$csv_sample") → $rows lines" >> "$VERIFY"
  ok "pre_landing CSV → $rows lines"
fi

step "2.6  Summary"
log "Per-area sizes:"
du -sh "$BACKUP_DIR/synapse/pre_landing" 2>/dev/null
du -sh "$BACKUP_DIR/synapse/stage1_transactional" 2>/dev/null
du -sh "$BACKUP_DIR/synapse/stage3_cubes" 2>/dev/null
echo
log "Total synapse backup:"
du -sh "$BACKUP_DIR/synapse"

echo
ok "SYNAPSE BACKUP COMPLETE"
log "Next: ./03-keyvault.sh"
