# Legacy Backup Scripts — How To Run

Four scripts. Run in order. Each is **idempotent** (safe to re-run) and **fail-fast** (stops at the first error so you don't end up with a half-backup).

```
backup-scripts/
├── .env.example          ← copy to .env, fill in values
├── lib.sh                ← shared helpers (logging, checks)
├── 00-preflight.sh       ← verify tools + creds + connections
├── 01-mssql.sh           ← backup all 7 MSSQL DBs, smoke-verify
├── 02-synapse.sh         ← backup Synapse Delta parquet
├── 03-keyvault.sh        ← backup + encrypt both Key Vaults
└── run-all.sh            ← driver: runs 00 → 03 with confirmation gates
```

## Quick start

```bash
cd "/Users/mac/Desktop/PS_P/gains-platform/data/legacy documentation/backup-scripts"

# 1) One-time setup
cp .env.example .env
# Edit .env in your editor — fill in the 5 values
chmod +x *.sh

# 2) Pre-flight (safe to re-run anytime)
./00-preflight.sh
#   → installs missing tools, prompts for missing creds, tests every connection
#   → exits 0 only when EVERYTHING is reachable

# 3) Run backups one at a time, or all at once
./01-mssql.sh         # ~30-60 min depending on DB size
./02-synapse.sh       # ~30-90 min depending on parquet size + network
./03-keyvault.sh      # ~5 min

# OR run them all in sequence with confirmation gates between steps:
./run-all.sh
```

## What gets created

```
~/Desktop/PS_P/legacy-backup-YYYYMMDD/
├── logs/                       per-step log files
├── mssql/                      .bak files + verify report
├── synapse/                    parquet trees
├── keyvault.age                encrypted secrets bundle
└── MANIFEST.md                 catalog (created at end of run-all.sh)
```

## Safety design

| Behaviour | How |
|---|---|
| Idempotent | Each script checks for existing output and skips work that's already done |
| Fail-fast | `set -euo pipefail` everywhere; first error aborts |
| Logged | Every script tees stdout+stderr to `logs/NN-name-TIMESTAMP.log` |
| No plaintext leak | Key Vault dump is encrypted in §3 and plaintext is shredded immediately |
| Resumable | If azcopy interrupts, re-running picks up where it left off |
| No prod writes | All scripts are READ-ONLY against legacy (BACKUP DATABASE writes to pod tmp, then we copy out and delete) |

## After all four pass

You're ready for the Azure tear-down — see `../AZURE_SHUTDOWN_AUDIT.md` §4 (the 9-step shutdown sequence).
