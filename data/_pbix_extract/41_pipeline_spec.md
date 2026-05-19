# Synapse Pipeline Spec — Schoology_Analytics

Source: `E:\Work\PS_P\gains\OEA\modules\module_catalog\Schoology_Analytics\` (pipeline JSONs, trigger JSONs, `setup.sh`, `set_names.sh`, plus the `Schoology_connector` / `Schoology_py.ipynb` notebooks the activities call into).

All Synapse activities call a single notebook reference `Schoology_connector` (which imports `Schoology_py`) with parameters `method_name`, `tables_source`, `kwargs`, and pass them to a Schoology class. The orchestrator pipeline `0_main_schoology` runs the whole stage1→stage3 transformation chain end-to-end. Pipelines `1`–`9` are individual stages of the same chain that can be run standalone (used for ad-hoc / scheduled invocations). `10_bulk_prelanding` is a separate scheduled bulk loader. `init` is a one-time SQL credential bootstrap.

---

## Section 1 — Pipeline DAG

`0_main_schoology` is the orchestrator. It runs activities **inside one pipeline** (no `ExecutePipeline` calls except the final PowerBI refresh). Numbered pipelines `1`–`9` are essentially the same notebook methods packaged as standalone pipelines, used by triggers / manual runs.

```
                        BlobEventsTrigger (Success.txt)
                                  |
                                  v
                       +----------------------+
                       |  0_main_schoology    |
                       |  (parameters:        |
                       |   workspace, version,|
                       |   folderPath,        |
                       |   fileName)          |
                       +----------+-----------+
                                  |
            (single-pipeline DAG, no ExecutePipeline until end)
                                  v
        [batch_completed_prelanding] -- preland_batch_comp_files
                                  |
                                  v
        [preprocess]              -- preprocess_schoology_dataset
                                  |
                                  v
        [ingestion]               -- ingest_schoology_dataset
                                  |
                                  v
        [dimension tables]        -- build_dimension_tables
                                  |
                                  v
        [facts tables]            -- build_fact_tables
                                  |
                                  v
        [cube tables]             -- cube_Build
                                  |
                                  v
        [powerBI_datasets_update]  ExecutePipeline -> powerBI_datasets_update
                                                       (NOT FOUND in this folder;
                                                        deployed separately by setup.sh)

  Independent pipelines (called by other triggers, not by 0_main):

   ScheduleTrigger (monthly, Stopped)         ScheduleTrigger (every 30 min)
            |                                              |
   +--------+--------+----------+                          v
   v                 v          v                +--------------------+
 1_load_users  2_load_roles  3_Standards          | 10_bulk_prelanding |
 (load_users)  (load_roles)  (load_standard)      | (preland_raw_folder)|
                                                  +--------------------+

   BlobEventsTrigger (.csv in pre_landing)
            |
            v
   +-----------------------+
   | 4_prelanding_schoology |  -- preland_schoology_csv (per-file)
   +-----------------------+

   Stand-alone debugging duplicates of 0_main steps (no triggers shipped):
     5_preprocessing_schoology    -- preprocess_schoology_dataset
     6_ingestion_schoology        -- ingest_schoology_dataset
     7_dimension_tables_schoology -- build_dimension_tables
     8_facts_tables_schoology     -- build_fact_tables
     9_cube_tables_schoology      -- cube_Build

   One-time bootstrap (no trigger):
     init  -- runs SQL CREATE CREDENTIAL on LS_SQL_Serverless
```

The only `ExecutePipeline` activity in the entire shipped set is `0_main_schoology → powerBI_datasets_update` (and that target pipeline is provisioned by `setup.sh` line 48 from a file the catalog ships separately). No pipeline calls another pipeline besides that.

---

## Section 2 — Per-pipeline detail

All notebook activities target Spark pool `spark3p3sm`, executor/driver size `Small`, dynamic allocation disabled, retry `0`, `retryIntervalInSeconds: 30`, `timeout: "0.12:00:00"` (12 hours). All call notebook `Schoology_connector` (except `3_Standards` which calls `Standards_connector`). I'll only list activity-level deltas below.

### `0_main_schoology` (orchestrator)

- **What it does:** End-to-end run for one trigger event — consumes the `Success.txt` batch file, prelands all CSVs listed in it, then preprocesses → ingests → builds dims → builds facts → builds cubes → kicks off PowerBI refresh.
- **Parameters:**

| Name        | Type   | Default | Source                                |
|-------------|--------|---------|---------------------------------------|
| workspace   | string | `dev`   | static                                |
| version     | string | `0.1`   | static                                |
| folderPath  | string | —       | `@triggerbody().folderPath`           |
| fileName    | string | —       | `@triggerbody().fileName`             |

- **Activities (all `SynapseNotebook`, in dependency order):**

  | Activity name              | depends_on            | method_name                  | tables_source                                                       |
  |----------------------------|-----------------------|------------------------------|---------------------------------------------------------------------|
  | batch_completed_prelanding | (none, root)          | `preland_batch_comp_files`   | n/a — passes `folderPath`, `fileName`                               |
  | preprocess                 | batch_completed_prel. | `preprocess_schoology_dataset` | `@concat('stage1/Transactional/schoology_raw/v',pipeline().parameters.version)` |
  | ingestion                  | preprocess            | `ingest_schoology_dataset`   | `@concat('schoology/v',pipeline().parameters.version)`              |
  | dimension tables           | ingestion             | `build_dimension_tables`     | `stage2/Ingested`                                                   |
  | facts tables               | dimension tables      | `build_fact_tables`          | `stage2/Ingested`                                                   |
  | cube tables                | facts tables          | `cube_Build`                 | (none — no tables_source param)                                     |
  | powerBI_datasets_update    | cube tables           | `ExecutePipeline` → `powerBI_datasets_update` (waitOnCompletion=true), passes `fileName` |

- The `kwargs` parameter is built as a literal Python-dict string, e.g. `{'tables_source':tables_source}` or `{'bcfileName':fileName, 'bcfolderPath':folderPath}` — referencing the activity's own param names rather than pipeline params (the notebook re-evaluates them).
- `concurrency: 10` at pipeline level. `snapshot: true` only on `batch_completed_prelanding`.

### `1_load_users_schoology`

- **What:** Calls Schoology REST API `/users` + `/users/inactive`, lands JSON at `schoology_raw/v{version}/users` as `oea.DELTA_BATCH_DATA` partitioned by `rundate`.
- **Activity:** one `SynapseNotebook` named `load_users`.
- **method_name:** `load_users`
- **No pipeline-level parameters**; uses notebook-internal `version=0.1`.

### `2_load_roles_schoology`

- **What:** Calls Schoology REST `/roles`, lands at `schoology_raw/v{version}/roles`.
- **Activity:** one `SynapseNotebook` named `load_roles` (`snapshot: true`).
- **method_name:** `load_roles`
- **No parameters.**

### `3_Standards`

- **What:** Loads standards from external API. Different notebook reference: `Standards_connector` (NOT `Schoology_connector`).
- **Activity:** one `SynapseNotebook` named `load_Standards` (`snapshot: true`).
- **method_name:** `load_standard`
- **No parameters.**

### `4_prelanding_schoology`

- **What:** Lands a single CSV from `pre_landing/Schoology/...` into stage1. Triggered per-file by the `.csv` Blob trigger.
- **Activity:** `preland_pipeline` (`SynapseNotebook`).
- **method_name:** `preland_schoology_csv`
- **Pipeline parameters:** `folderPath: string`, `fileName: string` (both wired from `@triggerbody()`).
- **kwargs:** `{'fileName':fileName, 'folderPath':folderPath}`

### `5_preprocessing_schoology`

- **What:** Standalone version of `0_main`'s preprocess step.
- **method_name:** `preprocess_schoology_dataset`
- **tables_source (hardcoded):** `stage1/Transactional/schoology_raw/v0.1`
- **No pipeline parameters.**

### `6_ingestion_schoology`

- **What:** Standalone version of `0_main`'s ingestion step.
- **method_name:** `ingest_schoology_dataset`
- **tables_source (hardcoded):** `schoology/v0.1`

### `7_dimension_tables_schoology`

- **method_name:** `build_dimension_tables`
- **tables_source:** `stage2/Ingested`

### `8_facts_tables_schoology`

- **method_name:** `build_fact_tables`
- **tables_source:** `stage2/Ingested`

### `9_cube_tables_schoology`

- **method_name:** `cube_Build` (no tables_source/kwargs)
- `snapshot: true`

### `10_bulk_prelanding`

- **What:** Walks `oea/Raw_Files/Schoology/<tenant>/...` recursively, prelands every `.csv` it finds (skipping `Done_Prelanding`), then moves the processed source folder into `Done_Prelanding/<YYYY-MM-DD>/`.
- **Activity:** `preland_raw_Files` (`SynapseNotebook`, `snapshot: true`).
- **method_name:** `preland_raw_folder`
- **No parameters.**

### `init`

- **What:** One-time bootstrap — issues `CREATE CREDENTIAL [https://<storage_account>.dfs.core.windows.net] WITH IDENTITY = 'Managed Identity'` against the SQL serverless pool.
- **Activity type:** `Script` (NOT `SynapseNotebook`) on `LS_SQL_Serverless`, parameter `dbName=master`, `scriptBlockExecutionTimeout: 02:00:00`.
- **Pipeline parameter:** `storage_account: string` (default `yourstorageaccount`, rewritten by `setup.sh` via `sed`).

---

## Section 3 — Trigger conditions

| Trigger file                                  | Type               | Pipeline triggered          | State    | Filter / schedule                                                                                                |
|----------------------------------------------|--------------------|-----------------------------|----------|------------------------------------------------------------------------------------------------------------------|
| `0_batch_prelanding_storage_trigger.json`    | `BlobEventsTrigger`| `0_main_schoology`          | Started  | `blobPathBeginsWith: /oea/blobs/pre_landing/`, `blobPathEndsWith: Success.txt`, event `Microsoft.Storage.BlobCreated`, `ignoreEmptyBlobs: true`. Passes `folderPath`, `fileName` from `@triggerbody()`. |
| `1_prelanding_storage_trigger.json`          | `BlobEventsTrigger`| `4_prelanding_schoology`    | Started  | `blobPathBeginsWith: /oea/blobs/pre_landing`, `blobPathEndsWith: .csv`, event `Microsoft.Storage.BlobCreated`. Passes `folderPath`, `fileName`. |
| `2_schedule_trigger_users_roles_standards.json` | `ScheduleTrigger` | `1_load_users_schoology`, `2_load_roles_schoology`, `3_Standards` (all three on the same trigger) | **Stopped** | `frequency: Month, interval: 1, startTime: 2025-01-01T12:40:00, timeZone: India Standard Time`. No cron, simple monthly recurrence. |
| `bulk_prelanding_trigger.json`               | `ScheduleTrigger`  | `10_bulk_prelanding`        | Started  | `frequency: Minute, interval: 30, startTime: 2025-04-30T15:41:00, timeZone: India Standard Time` — every 30 minutes. |

Important nuances:

- **No per-school path filter.** Both blob triggers fire on anything under `pre_landing/`. Per-school separation exists only inside the file path (`pre-landing/Schoology/{tenant}/Year.../...csv`) and is parsed by the notebook, not by the trigger.
- The `Success.txt` trigger and the `.csv` trigger both match the same blob root `pre_landing/`, but the `Success.txt` trigger requires the literal trailing `Success.txt` to fire `0_main`. The CSVs that arrive earlier individually fire `4_prelanding_schoology`. So in practice each CSV is prelanded twice on a real run: once by the blob-arrival trigger, again when `0_main` walks the batch list. (This is what the catalog ships; if intent is "only the batch trigger does the prelanding", the per-CSV trigger should be disabled.)
- `scope` field in both blob triggers is a placeholder string `"/subscriptions/@subscriptionId/resourceGroups/@resourceGroupName/providers/Microsoft.Storage/storageAccounts/@storageAccountName"`. `setup.sh` sed-substitutes those literals with the runtime values.
- The schedule-trigger JSON has a stray blank line between role and standard pipeline references (line 19 is empty) — harmless but worth knowing.

---

## Section 4 — Parameters and per-school configuration

### Parameter names `0_main_schoology` accepts

| Parameter   | Type   | Default | Set by                    |
|-------------|--------|---------|---------------------------|
| workspace   | string | `dev`   | static / never overridden |
| version     | string | `0.1`   | static                    |
| folderPath  | string | —       | trigger body              |
| fileName    | string | —       | trigger body              |

There is **no `school_id` or `tenant` pipeline parameter anywhere**. The pipeline is single-tenant from the orchestration layer's perspective. Per-school logic lives entirely inside the notebook:

- The pre-landing folder convention is `pre-landing/Schoology/{tenant}/Year-.../...` (see `Schoology_py.ipynb` line ~470 docstring). The first path segment after `Schoology/` carries the tenant identifier; the notebook splits `File_Path` by `/` and pulls `Session`, `Assessment_type`, `Subject`, `Grade`, `Section`, `File_Name` from positions 0–5 (`preprocess_schoology_dataset`, lines ~199–210).
- Three school IDs are **hardcoded** in `Schoology_py.ipynb` for an instructor-name normalisation hack (line ~402):
  - `186370968` → Athenian (`teacher_dict_athenian`)
  - `7448280461` → Brightview (`teacher_dict_brightview`)
  - `7368546879` → Southprep (`teacher_dict_southprep`)
- Per-tenant configuration (subject overrides, subject↔course-name mapping) is fetched at build-dimension time from `https://api.edvancelearning.us/Reporting/api/app/tenant-config/tenant-config/{tenant_id}?key=SubjectOverrideConfigJson` and `?key=MapSubjectWithCourseNameJson`. `tenant_id` is read out of the dim table `dim_school_tenant` (line ~231). So tenants are discovered from data, not configured at the pipeline level.
- `workspace` parameter (defaults to `dev`) is interpolated into Key Vault secret names: `schoologyConsumerKey{workspace}`, `schoologyOauthSignature{workspace}` (constructor at line 49 of `Schoology_py.ipynb`). So `workspace='dev'` resolves to `schoologyConsumerKeydev` etc. — and `setup.sh` line 79 only writes the `dev` variants. Production switch would mean either changing the default or writing additional `*prod` secrets.

### Hardcoded paths in `setup.sh`

- `kv-oea-${org_id_lowercase}` — Key Vault name
- `stoea${org_id_lowercase}` — storage account name
- `rg-oea-${org_id_lowercase}` — resource group name
- `pre_landing/Schoology` — directory that gets created at the end (line 85)
- `oea` filesystem (line 85)
- Notebook names: `Schoology_connector`, `Schoology_py`
- Spark pool: `spark3p3sm`
- A leaked-looking placeholder consumer key `ab756abd...` and signature `98fb99342...` are written verbatim as `schoologyConsumerKeydev` / `schoologyOauthSignaturedev` (lines 78–81). Treat as test/sample values that must be overwritten before any production use.

`set_names.sh` only exports environment variables (no school references):
- `OEA_VERSION=0.8dev`
- `OEA_RESOURCE_GROUP`, `OEA_SYNAPSE`, `OEA_STORAGE_ACCOUNT`, `OEA_ML_WORKSPACE`, `OEA_KEYVAULT`, `OEA_ML_STORAGE_ACCOUNT`, `OEA_APP_INSIGHTS`, `OEA_ADDITIONAL_TAGS`. All keyed off the `org_id` argument.

---

## Section 5 — Execution semantics

- **Granularity:** Mostly **per-batch**. A run of `0_main_schoology` is triggered by *one* `Success.txt` upload. That `Success.txt` lists (`folder_path,file_name` per line) all the CSVs in the batch; `preland_batch_comp_files` reads the file and iterates them. The downstream stages (`preprocess`, `ingest`, `build_dim`, `build_fact`, `cube`) operate on **all data at the configured `tables_source` path**, not on a single file — they walk the folder tree and process every entity. So:
  - Pre-landing is per-file (loop inside one activity).
  - Preprocess/ingest/dim/fact/cube are per-batch and effectively cross-tenant in one go.
  - The per-CSV `1_prelanding_storage_trigger` provides a per-file fallback path.
- **Failure model:** All `dependsOn` conditions are `Completed` only — meaning "succeeded or failed". (Synapse interprets `Completed` as terminal-but-permissive in some places; in this JSON the activities chain on `Completed`, so a failed `preprocess` will *not* automatically gate `ingestion`. Verify on Synapse runtime.) Inside `preland_batch_comp_files` each per-file call is wrapped in `try/except AnalysisException` and logs and continues — a single missing file does **not** kill the run. Inside `preprocess_schoology_dataset` there is no per-item try/except, so a malformed entity folder *can* fail the whole batch. `retry: 0` everywhere — no automatic re-run.
- **Idempotency:** Notebooks are idempotent for re-runs of the same dataset because:
  - Stage1 lands using `oea.land(...)` partitioned by `rundate=YYYY-MM-DD` (overwrite for that rundate).
  - Stage2/Stage3 use `oea.upsert(df, destination, primary_key)` (`_publish_to_stage2` / `_publish_to_stage3`, lines 769–772).
  - `delete_stale_rows()` (line 729) does a Delta `MERGE … WHEN MATCHED DELETE` against rows present in destination but not in incoming `source_df`, restricted by `req_cols` (typically `[School_ID, Question_ID, Standards]`). This makes the merge "full-replace within scope of incoming keys" — safe for idempotent reruns of the same source data, but **destructive** if the incoming source is partial. Used in dim_question_data, fact_student_submission, Cube_Question_Summary, Cube_OverallPerformance_Summary, Cube_User_Summary.
- **Concurrency:** `concurrency: 10` set on `0_main_schoology`. Other pipelines have no explicit concurrency limit. The 30-minute scheduled `bulk_prelanding_trigger` could overlap with itself if a run takes >30 min — no guard. The blob trigger could fire `0_main` many times in parallel for back-to-back uploads; Synapse will queue beyond the workspace's per-pipeline concurrency limit. Spark pool is `spark3p3sm` with `executorSize: Small`.

---

## Section 6 — `setup.sh` and `set_names.sh`

### `setup.sh` (35 effective steps, summarised)

1. **Args:** `setup.sh <synapse_workspace_name> <org_id>`. Lower-cases `org_id` into `org_id_lowercase` and derives `OEA_KEYVAULT=kv-oea-${org_id_lowercase}`, `OEA_STORAGE_ACCOUNT=stoea${org_id_lowercase}`, `resource_group_name=rg-oea-${org_id_lowercase}`. Pulls subscription ID from `az account show`.
2. **Notebooks:** `az synapse notebook import` for `Schoology_connector` and `Schoology_py` (both bound to spark pool `spark3p3sm`).
3. **Pipelines:** Imports pipelines `1`–`9` first, then `0_main_schoology`, then `10_bulk_prelanding`, then `powerBI_datasets_update`. Order matters because `0_main` references `powerBI_datasets_update` — but `setup.sh` actually creates `0_main` *before* `powerBI_datasets_update` (line 45 vs 48). This works because Synapse's `pipeline create` doesn't validate cross-references at deploy time; the dependency is only resolved at run time.
4. **`init` pipeline:** Sed-substitutes `yourstorageaccount` → `$OEA_STORAGE_ACCOUNT` into `tmp/init.json`, then deploys.
5. **Triggers:** Sed-substitutes `@subscriptionId`, `@resourceGroupName`, `@storageAccountName` placeholders in the two blob trigger JSONs (lines 55–62). Note line 64 mistakenly uses the *unsubstituted* `0_batch_prelanding_storage_trigger3.json` from the original `triggers/` folder rather than the freshly-rewritten one in `tmp/` — likely a bug in the script. The other three triggers are deployed and started.
6. **Secrets — Key Vault:**
   - Vault: `kv-oea-${org_id_lowercase}` (set as `$OEA_KEYVAULT`).
   - `schoologyConsumerKeydev` ← hardcoded `ab756abd3cc5a20fc6d298a23b885e220653a1dbd`
   - `schoologyOauthSignaturedev` ← hardcoded `98fb99342dce0abb6adbd6903d72d053%26`
   - Both reference the `dev` workspace suffix only. Production deployment must add `schoologyConsumerKeyprod` / `schoologyOauthSignatureprod`.
7. **Storage:** `az storage fs directory create -n pre_landing/Schoology -f oea --account-name $OEA_STORAGE_ACCOUNT`.

**No `Athenian`/`edls1` references anywhere in either shell script** (I grepped the whole module — zero matches; the school-specific names live only in `Schoology_py.ipynb` as data-driven mappings keyed on numeric `school_id`).

### `set_names.sh`

Pure naming-convention export script. Sets `OEA_VERSION=0.8dev` and the eight `OEA_*` variables (resource group, synapse, storage, ML workspace, keyvault, ML storage, app insights, additional tags). All names are `<prefix>-${org_id}` or `<prefix>${org_id_lowercase}`.

---

## Section 7 — Mapping to a Python-on-Railway rebuild

Goal: replace the entire Synapse + Spark + Delta pipeline with a single ingestion service that runs on Railway, hits Postgres / object storage, and reproduces `0_main_schoology` end-to-end.

### Trigger replacement

| Synapse trigger                              | Railway equivalent                                                                                                                               |
|----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `0_batch_prelanding_storage_trigger`         | Object-storage event → webhook (e.g. S3/MinIO event → Railway HTTP endpoint), filter on `key endsWith Success.txt` and `key startsWith pre_landing/`. Or: a polling worker that lists prelanding for new `Success.txt` keys every minute. |
| `1_prelanding_storage_trigger` (per-CSV)     | Drop entirely — it's redundant with the batch trigger and double-prelands. Keep only the batch path.                                            |
| `2_schedule_trigger_users_roles_standards`   | Cron worker, monthly. Currently `Stopped` in Synapse, so probably not load-bearing.                                                              |
| `bulk_prelanding_trigger`                    | Cron worker, every 30 min (or change to event-driven if the bulk folder also emits events).                                                      |

### Job structure

One Python job `run_main(folder_path: str, file_name: str, version="0.1", workspace="dev")` that internally runs these steps in order, each as a function (mirrors notebook methods):

1. `preland_batch(folder_path, file_name)` — read the success-list text file, iterate `(folder, file)` lines, call `preland_csv` for each. Wrap each call in try/except and log failures (matches existing behaviour).
2. `preland_csv(folder, file)` — read CSV (UTF-8, with the same `quote/escape/multiLine` semantics), apply `Question` truncation to 7500 chars, the per-question-type Standards melt, instructor normalisation (with the three hardcoded `school_id`→teacher dict mappings), and write to `stage1/Transactional/schoology/v{version}/{item}/rundate=YYYY-MM-DD/`.
3. `preprocess(version)` — walk the stage1 folder, do per-entity adhoc transformations (cast `parents`/`links` columns for users/roles, regex strip on standards.description, derive `Session/Assessment_type/Subject/Grade/Section/File_Name` from `File_Path` for `question_data`/`student_submissions`/`submission_summary`).
4. `ingest(version)` — promote stage1 → `stage2/Ingested/schoology/v{version}/{item}` with light schema enforcement.
5. `build_dimension_tables()` — over `stage2/Ingested`, build `dim_*` tables and call upsert + `delete_stale_rows` for `dim_question_data`. Fetch tenant configs from `https://api.edvancelearning.us/Reporting/api/app/tenant-config/...` keyed off `dim_school_tenant`.
6. `build_fact_tables()` — build `fact_student_submission`, upsert + `delete_stale_rows`.
7. `cube_build()` — build `Cube_Question_Summary`, `Cube_Question_Summary_Overall`, `Cube_OverallPerformance_Summary`, `Cube_User_Summary` from the published facts; upsert each.
8. `refresh_powerbi(file_name)` — POST to PowerBI REST API to refresh datasets. (Replaces `powerBI_datasets_update` ExecutePipeline.)

### Storage / compute mapping

- ADLS Gen2 (`pre_landing/`, `stage1/Transactional/`, `stage2/Ingested/`, `stage2/Enriched/`, `stage3/Published/`) → object storage (S3/Cloudflare R2) with the same prefix convention, OR Postgres tables if the volumes are small enough. Given Delta `MERGE WHEN MATCHED DELETE` is the semantics, Postgres `INSERT ... ON CONFLICT DO UPDATE` + a scoped `DELETE WHERE (school_id, question_id) IN (...)` precisely replaces `delete_stale_rows`.
- Spark + Delta → Polars or DuckDB for in-process columnar processing; pandas for the per-CSV melt step (already pandas in the notebook). No Spark cluster needed for the data sizes implied.
- Synapse Notebook activity → plain Python function call. The `method_name`/`kwargs` indirection in the JSON is an artefact of Synapse's parameterised notebook model and can be dropped entirely.

### Secrets

Replace Key Vault secrets `schoologyConsumerKey{workspace}` / `schoologyOauthSignature{workspace}` with environment variables `SCHOOLOGY_CONSUMER_KEY` / `SCHOOLOGY_OAUTH_SIGNATURE` (per environment). Same OAuth1 PLAINTEXT auth header construction.

### Idempotency / retries

- All writes use upsert by primary key.
- Wrap the batch in a single transaction-id (e.g. `run_id = uuid4()`); store it on every row inserted/updated this run. Re-running with the same `success_file` is safe.
- Replace per-activity `retry: 0` with worker-level retry policy (e.g. retry 3× on transient HTTP errors against Schoology API, no retry on data errors — log and continue, matching current behaviour).

### Concurrency

- Single worker per `Success.txt`, queue if more than one arrives. (Matches Synapse's effective serial-per-trigger behaviour.)
- The bulk loader (`preland_raw_folder`) on a separate scheduled worker, with overlap guard (skip if previous still running).

### Observability

- Replace `logger.info` calls with structured logs (JSON) — they already exist throughout the notebook.
- Track per-run metrics: rows in / rows out / new-inbound count (the notebook already returns `number_of_new_inbound_rows` from `publish()`).
- Surface failures of the per-CSV try/except as warnings in run summary, not silent.

### Items not currently parameterised that probably should be in the rebuild

- `version` (currently always `0.1`, baked in everywhere).
- `workspace` (currently always `dev`).
- The three hardcoded school IDs and their teacher dictionaries — externalise to a config table keyed by `school_id` (tenant config endpoint already exists at `api.edvancelearning.us/.../tenant-config/{tenant_id}`; extend it to carry the teacher-normalisation map too).

### Out-of-scope sanity checks

- The `init.json` SQL credential pipeline does not exist in a Postgres world — drop it. The Synapse-equivalent `CREATE CREDENTIAL ... Managed Identity` is already replaced by Railway/IAM service account auth on the storage side.
- `powerBI_datasets_update.json` is referenced by `setup.sh` line 48 but **NOT FOUND** in `pipeline/` — implement directly as a PowerBI REST `POST /datasets/{id}/refreshes` call from Python; do not try to extract the missing pipeline.
