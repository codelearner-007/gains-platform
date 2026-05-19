# Companion Modules Spec — LMS_py, Standards_py, Connectors

**Source files inspected:**
- `E:\Work\PS_P\gains\OEA\modules\module_catalog\EdvanceLS\notebook\LMS\LMS_py.ipynb`
- `E:\Work\PS_P\gains\OEA\modules\module_catalog\EdvanceLS\notebook\LMS\LMS_connector.ipynb`
- `E:\Work\PS_P\gains\OEA\modules\module_catalog\EdvanceLS\notebook\Standards\Standards_py.ipynb`
- `E:\Work\PS_P\gains\OEA\modules\module_catalog\EdvanceLS\notebook\Standards\Standards_connector.ipynb`
- `E:\Work\PS_P\gains\OEA\modules\module_catalog\Schoology_Analytics\notebook\Schoology_connector.ipynb`

**Headline finding:** `LMS_py` is NOT a "users + roles + courses sync from external LMS" as the prompt assumed. It is an **end-to-end Edvance LMS analytics pipeline** (questions, quizzes, users, courses, submissions, plus a full set of dim/fact/agg tables) that is **structurally independent of `Schoology_py.ipynb`**. The two pipelines share the same OEA lake but produce parallel branded outputs (`Schoology_*` vs `LMS_*`). Only `Standards_py.ipynb` is genuinely shared — it is `%run` from `LMS_py` and is also the source of the standards joined into `dim_standard` for both pipelines (via the Edvance "Case Network" API).

---

## Section 1 — `LMS_py.ipynb`

### 1.1 What it loads

It pulls a single fat JSON from the Edvance LMS course-analytics endpoint and explodes it into four base DataFrames:

| Output DF | What it is |
|---|---|
| `questions_df` | Quiz/question bank: `Item_ID`, `Item_Type`, `QuizID`, `quizType`, `quizName`, `Question_ID`, `Question`, `answerOptions`, `answer`, plus exploded `option_no` + `Options` |
| `users_df` | LMS users: `organizationId` (prefixed `LMS_`), `firstName`, `lastName`, `college`, `fullName`, `emailAddress`, `points`, `collegeId`, `id` |
| `student_submissions` | One row per (user × quiz × question), with `score`, `IsCorrect`, `Points_Possible`, `Points_Received`, `UserAnswerOption`, `CorrectAnswerOption`, `Standards` |
| `courses_df` | `categoryId`, `categoryName` (= grade), `courseId`, `courseName` (= subject) |

So yes, it loads users **and** courses **and** assessment submissions — but it is **not the Schoology user/section/role roster source**. Schoology has its own `/users`, `/sections`, `/enrollments` calls inside `Schoology_py.ipynb`. There is **no overlap of user IDs** between the two — Edvance LMS users carry `organizationId = "LMS_<n>"`, Schoology users carry the Schoology school org id.

### 1.2 Source

REST API to the **Edvance Learning** SaaS, OAuth2 client_credentials:

```python
self.baseurl = "https://api.edvancelearning.us/LMS/api/app/course-analytics/"
self.tokenurl = "https://auth.edvancelearning.us/connect/token"
...
api_url = f"{self.baseurl}course-analysis"
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get(api_url, headers=headers)
```

Credentials come from Azure Key Vault via `oea._get_secret`:

```python
self.keyvault_consumer_key = f'caseNetworkConsumerKey{workspace}'
self.keyvault_consumer_secret = f'caseNetworkConsumerSecret{workspace}'
```

(Note the secret names say `caseNetwork…` — same vault entry is reused for both LMS and Standards; see Section 2.)

The single `course-analysis` response contains four top-level keys traversed by the loader:
- `lms["roots"]` → questions
- `lms["userDtos"]` → users
- `lms["userQuizProgressInfo"]` → submissions
- `lms["courseDetail"]` → courses

There is **no CSV / blob / SAS source**. Everything is API-driven and `oea.land()` is **never** called inside `LMS_py.lms_load_tables()` — i.e., it does **not write a stage1 raw landing**, it directly produces in-memory Spark DataFrames.

### 1.3 What it outputs (table catalog)

`LMS` class methods build three layers of tables. None are explicitly persisted in the cells we see (no `oea.write` / `df.write.format("delta").save(...)` calls), so the outputs are **in-memory `self.*` attributes** that downstream notebooks (or the connector) presumably persist via OEA helpers not shown here.

**Dimension tables (`lms_dimension_tables`):**

| Table | Key columns | Notes |
|---|---|---|
| `course_user_org` | `Course_ID`, `user_Id`, `organizationId` | Bridge built from submissions |
| `dim_grade` | `Course_ID`, `organizationId`, `Grade`, `GradeID` | From `courses_df.categoryName` |
| `dim_item` | `Item_ID`, `Item_Type`, `Item_Name`, `organizationId="hard_code_LMS_1"` | Hard-coded org |
| `dim_question_data` | `Question_ID`, `quiz_Id`, `Question`, `Question_No`, `Correct_Answer`, `Standards`, `Item_ID`, `Item_Name`, `Subject`, `Grade`, `Session="hard_code_2022-23"`, `Question_Type="Multiple Choice"`, `Least_Points_Earned`, `Average_Points_Earned`, `Most_Points_Earned`, `Total_Points`, `Correctly_Answered`, `Qkey` | Heavily synthesized |
| `dim_standard` | passthrough of `stand_df` with `Schoology_Standard` renamed to `Standards` | **Same shape as Schoology's dim_standard** |
| `dim_student` | `id`, `organizationId`, `firstName`, `lastName`, `college`, `fullName`, `emailAddress`, `points`, `collegeId` | From `users_df` |
| `dim_subject` | `subjectID`, `Subject`, `orgID` | |
| `dim_unit_lesson` | `Item_ID`, `Item_Name`, `organizationId` | |
| `dim_assessment` | `assessment_ID`, `assessment_type`, `organizationId` | |
| `dim_section` | `Section_NID="hard_code_500"`, `Section_Code=3`, `Section_Instructors="Carissa Farrell"`, `organizationId="LMS_hadrcode_1"` | Entirely hard-coded single-row DF |

**Fact table (`lms_fact_tables`):**

| Table | Notable columns |
|---|---|
| `fact_student_submission` | `Course_NID`, `User_UID`, `Question_Id`, `Assessment_type`, `Answer_Submission`, `Correct_Answer`, `Points_Possible`, `Points_Received`, `Submission_Grade`, `Section_NID="hard_code_100"`, `section=1`, `Section_Instructors="Carissa Farrell"`, `Session="hard_code_2022-23"`, `Section_Code="hard_code_3"`, `Submission="hard_code_1"`, `User_id_ques_id` |

**Aggregate tables (`lms_aggregate_tables`):**
- `agg_total_student`
- `StandardByDeep_Dive` (a.k.a. `agg_Correct_Incorrect_Answer_By_Standard`)
- `StandardByStrand` (a.k.a. `agg_Correct_Incorrect_Answer_By_Strand`)
- `agg_question_summary_report` (composed inside `submissions_df` near end)
- `agg_Grade_Performance_by_Strand` (the `grouped_df` block)
- `agg_question_response_analysis` (`ques_stand_desc_secID_inst`)
- `agg_Incorrect_Details` (two tables: `incorrect_students_df_perc_item` and `incorrect_submissions_names`)
- `agg_submission_summary` (`submission_summ`)

**No primary keys are declared** anywhere — Spark DataFrames, no `PRIMARY KEY` constraints. De-facto keys are `User_UID + Question_ID + quiz_Id` for the fact table.

### 1.4 How `Schoology_py.ipynb` consumes its output

**It does not.** `LMS_py` and `Schoology_py` are siblings, not parent/child. They share:

1. **`Standards_py`** (loaded by `LMS_py` via `%run Standards_py`; `Schoology_py` loads it identically — see Section 4).
2. **The `oea` lake helper** (i.e., they live in the same OEA workspace and write to the same lakehouse via the same conventions).
3. **`dim_standard` schema** — both pipelines call `edvanceLs.lms_load_standard()` and produce a `dim_standard` table with the same columns.

There is **no** code in `LMS_py` that reads a `Schoology/*` path, and no code in this notebook that writes to a path Schoology depends on (`oea.land` calls inside `LMS_py` — NOT FOUND in the cell content shown).

### 1.5 Filter rules (role_id, etc.)

NOT FOUND. There are **no role filters** in `LMS_py`. The only filters applied to source data are:

```python
userQuizProgress_df = userQuizProgress_df.filter(size(userQuizProgress_df["StandardID"]) > 0)
```
(drop submissions whose question has no standard tagged)

```python
incorrect_submissions = all_student_submissions_df[
    student_submissions_df['Points_Received'] != student_submissions_df['Points_Possible']
]
```
(downstream agg only)

So the `role_id IN (...)` student filter that exists in `Schoology_py` is **not present here** — Edvance users have no role concept exposed in the `userDtos` payload.

---

## Section 2 — `Standards_py.ipynb`

### 2.1 Source

REST API on a **different Edvance endpoint** — the local CASE Network mirror:

```python
self.baseurl = "https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/"
self.tokenurl = "https://auth.edvancelearning.us/connect/token"
...
api_url = f"{self.baseurl}local-standards"
```

Same OAuth2 client_credentials flow, same `caseNetworkConsumerKey/Secret` Key Vault secrets. The response is a CASE-CF (Competency Framework) JSON: `cFDocument` → `items` (gradeLevel) → `children` (strand) → `children` (cluster) → `children` (standard).

So: it is the **CASE Network standards, served via Edvance's local mirror API** — not directly from CASE Network itself, not from a CSV, not hardcoded.

### 2.2 Output table

Single output: a JSON list landed to `oea` stage1:

```python
oea.land(json.dumps(standards),
         f'lms_raw/v{self.version}/standards',
         'standards.json',
         oea.DELTA_BATCH_DATA, currentDateTime)
```

The in-memory list is also returned (and consumed by `LMS_py` and `Schoology_py` directly via `edvanceLs.lms_load_standard()` returning a list of dicts which they wrap as `spark.createDataFrame(standards)`).

### 2.3 Schema (verify against PBIX `dim_standard`)

Each standard object built in `load_standard()`:

```python
standardObj = {
    'Identifier': standard["identifier"],
    'Language': standard["language"],
    'Schoology_Standard': standard["title"],
    'cPalms_Standard': cpalmsStandard,        # title split on '.', join from index 2
    'description': standard["description"],
    'cluster': cluster["title"],
    'Subject': cfdocument["cFDocument"]["subject"][0],
    'Grader': gradeLevel["title"],
    'Strand': strand["title"],
    'Cognitive_Complexity_Rating': '',        # always empty
    'lastChangeDateTime': standard["lastChangeDateTime"],
    'Direct_Link': cfdocument["cFDocument"]["uri"],
    'Standard_New': shortStandard             # title split, join from index 4
}
```

| Column | Source | Notes |
|---|---|---|
| `Identifier` | API `identifier` | Used as join key against `userQuizProgressInfo[].resultItems[].standardId` |
| `Language` | API `language` | |
| `Schoology_Standard` | API `title` | Renamed to `Standards` downstream |
| `cPalms_Standard` | derived | `".".join(title.split(".")[2:])` |
| `description` | API `description` | |
| `cluster` | parent `cluster.title` | |
| `Subject` | `cFDocument.subject[0]` | |
| `Grader` | parent `gradeLevel.title` | typo — should be "Grade" |
| `Strand` | parent `strand.title` | |
| `Cognitive_Complexity_Rating` | hardcoded `''` | **Always empty in source** |
| `lastChangeDateTime` | API | |
| `Direct_Link` | `cFDocument.uri` | |
| `Standard_New` | derived | `".".join(title.split(".")[4:])` |

**Verifies the PBIX `dim_standard` columns originate here**, except `Cognitive_Complexity_Rating` which is never populated by this loader (would need to come from elsewhere or remain blank).

### 2.4 Refresh cadence

NOT FOUND in the notebook itself — there is no scheduling metadata. Cadence is governed externally by the OEA pipeline / Synapse pipeline that invokes `Standards_connector.ipynb`. Inside `load_standard()`, only a `currentDateTime` stamp is captured for the landing path:

```python
currentDate = datetime.datetime.now()
currentDateTime = currentDate.strftime("%Y-%m-%d")
```

So the landed file is partitioned by ingestion date but the trigger schedule lives outside this notebook.

### 2.5 Class layout

The class is named `EdvanceLS` (not `Standards`), exposed as `edvanceLs = EdvanceLS()`. Its public methods: `set_workspace`, `set_version`, `get_access_token`, `fetch_standard`, `load_standard`. Note `LMS_py` calls `edvanceLs.lms_load_standard()` — that method name is **not defined** in the cells we see; either it is an alias added elsewhere or `LMS_py` actually expects `load_standard()` and the extracted notebook content is from a slightly different version. Worth verifying when reimplementing.

---

## Section 3 — Connectors

All three `*_connector.ipynb` files are **identical thin parameterized wrappers** used by Synapse pipelines as activity entry points. Pattern:

```python
# Cell 1 — pipeline params
workspace = 'dev'
version = '0.1'
method_name = None
kwargs = '{}'

# Cell 2 — load the framework class
%run /LMS_py     # or /Standards_py, /Schoology_py

# Cell 3 — apply workspace
lms.set_workspace(workspace)
lms.set_version(version)

# Cell 4 — dispatch and exit
m = getattr(lms, method_name)
kwargs = eval(kwargs)
result = m(**kwargs)
mssparkutils.notebook.exit(result)
```

So the connector:
- Receives `workspace`, `version`, `method_name`, `kwargs` from the parent Synapse pipeline.
- `%run`s the framework notebook to instantiate the singleton (`lms`, `edvanceLs`, or `schoology`).
- Calls the requested method via `getattr` and exits the returned value back to the pipeline.

**Environment / Key Vault loading:** Not done explicitly in connectors. Secrets are pulled lazily by `get_access_token()` inside each framework class via `oea._get_secret(<keyvault_key>)`. The Key Vault binding is configured at the Synapse linked-service level, not in notebook code. The only env-like values are `workspace` (used as a suffix on secret names: `caseNetworkConsumerKeydev` vs `caseNetworkConsumerKeyprod`) and `version` (used in lake paths like `lms_raw/v0.1/standards`).

The connectors share an even bigger oddity: the **`Standards_connector.ipynb` and `Schoology_connector.ipynb` both have the markdown title "Schoology connector"** (copy-paste artefact). The Standards one runs `%run /Standards_py` on the `edvanceLs` object, the Schoology one runs `%run /Schoology_py` on the `schoology` object.

---

## Section 4 — Dependencies on `Schoology_py`

### 4.1 Explicit cross-module references

`LMS_py.ipynb` cell 2:

```python
%run Standards_py
```

…and cell 3:

```python
standards = edvanceLs.lms_load_standard()
stand_df = spark.createDataFrame(standards)
stand_df = stand_df.withColumn('description', regexp_replace(stand_df['description'], r'\\r\\n', ' '))
```

This means **`LMS_py` requires `Standards_py` to be loaded first** (in the same Spark session). Same is true for `Schoology_py.ipynb` (per its own `%run Standards_py` — confirmed in earlier extract specs).

### 4.2 Shared lake outputs

Searching the `LMS_py` cell content for `oea.load(` calls referring to Schoology paths: **NOT FOUND**. Searching for `oea.load(` referring to LMS paths: **NOT FOUND** in this notebook (it builds DataFrames in-memory; landing/loading happens elsewhere or via methods not exercised in the cell sample).

### 4.3 Order of operations

Implied DAG (no explicit pipeline JSON in scope, but inferable from `%run` chains):

```
Standards_py.ipynb            (independent, runs first)
       │
       ├─► LMS_py.ipynb        (uses standards via stand_df; produces LMS dim/fact/agg)
       │
       └─► Schoology_py.ipynb  (uses standards via stand_df; produces Schoology dim/fact/agg)
```

`LMS_py` does **not** depend on `Schoology_py` and vice versa. Both depend on `Standards_py`.

### 4.4 What this means for "did Schoology_py expect LMS_py to have run?"

**No.** Schoology_py reads from Schoology's REST API and from its own stage1 landing. It does not consume any `LMS_*` table, role list, or roster. The earlier worry that `LMS_py` provides users/roles to Schoology is unfounded by the code. They are independent vertical pipelines with a shared standards dimension.

---

## Section 5 — Implications for our Postgres + Python rebuild

### 5.1 Do we need a separate "users sync" job?

**No** — for the Schoology pipeline. Schoology users come from the Schoology REST API directly inside `Schoology_py.ipynb` (its own `/users`, `/sections`, `/enrollments` calls). LMS users (Edvance) are a *different* user population for a *different* analytics product (the Edvance LMS dashboards). If we are only rebuilding Schoology, we can skip Edvance user sync entirely.

**Yes** — if we are also rebuilding the Edvance LMS analytics dashboards. Then we need a separate ingestion job that hits `https://api.edvancelearning.us/LMS/api/app/course-analytics/course-analysis` and explodes the four sections (`roots`, `userDtos`, `userQuizProgressInfo`, `courseDetail`) into Postgres tables.

### 5.2 Do we need a "standards sync" job?

**Yes — required for both pipelines.** `dim_standard` is non-optional in PBIX joins (`Standards`, `Strand`, `Cluster`, `cPalms_Standard`, `Description`). It must come from somewhere, and the only known source is `https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/local-standards`. Plan a small standalone job:

| Concern | Recommendation |
|---|---|
| Cadence | Weekly (standards rarely change; `lastChangeDateTime` per row lets us upsert) |
| Storage | One Postgres table `dim_standard` keyed on `identifier` (UUID v7 surrogate, natural unique on `identifier`) |
| Auth | OAuth2 client_credentials to `auth.edvancelearning.us/connect/token`, scope `LMSService` |
| Secret | Stored in our secrets manager (Supabase vault or env), keys named like the legacy ones (`CASE_NETWORK_CONSUMER_KEY`, `CASE_NETWORK_CONSUMER_SECRET`) |
| Dependency order | Run standards-sync → schoology-ingest (FK enforcement on `fact_student_submission.standard_id` → `dim_standard.identifier`) |

### 5.3 Or can we collapse all of this into one ingestion job?

For **Schoology-only rebuild**: collapse to two jobs — `standards_sync` (small, weekly) and `schoology_ingest` (larger, daily). One ingestion job is fine if we accept that the standards refresh is bundled at the start of every Schoology run; the trade-off is wasted API calls. Two jobs with proper scheduling is cleaner.

For **full parity with the legacy OEA setup**: three jobs, mirroring the notebook DAG:

```
standards_sync   ──┐
                   ├─► schoology_ingest  ──► schoology_marts (dim/fact/agg)
                   └─► edvance_lms_ingest ─► edvance_lms_marts (dim/fact/agg)
```

### 5.4 External APIs we MUST integrate

| API | Host | Purpose | Auth | Required for |
|---|---|---|---|---|
| Schoology REST API | `api.schoology.com` | Users, sections, enrollments, grades, grading_categories, attendance | OAuth1 two-legged (consumer key/secret) | All Schoology data |
| Edvance Local CASE Network | `api.edvancelearning.us/LMS/api/app/local-case-network-standards/` | Academic standards | OAuth2 client_credentials, scope `LMSService` | `dim_standard` for both Schoology and Edvance |
| Edvance LMS Course-Analytics | `api.edvancelearning.us/LMS/api/app/course-analytics/` | Edvance quiz/question/user/submission/course bank | Same OAuth2 token | Only if we rebuild Edvance LMS dashboards |

There is **no internal "MCT API"** referenced anywhere in the companion notebooks. **No CASE Network direct call** either — it goes through Edvance's mirror.

### 5.5 Other rebuild notes

- The legacy code has many **hard-coded values** in `LMS_py` (`Section_NID="hard_code_100"`, `Section_Instructors="Carissa Farrell"`, `Session="hard_code_2022-23"`, `Section_Code=3`). These are placeholders the original author left in because Edvance LMS does not expose section/session/instructor — if we rebuild this pipeline, decide whether to (a) carry the constants, (b) join from a manually maintained Postgres reference table, or (c) drop the columns.
- The class `Standards_py` defines `EdvanceLS.load_standard()` but `LMS_py` calls `edvanceLs.lms_load_standard()`. The mismatch suggests either a renamed method in a newer version of the file or a previous `lms_load_standard` alias. **Verify and unify naming** in our rebuild — one method, one name.
- `Cognitive_Complexity_Rating` is **always empty** from the source. If PBIX shows non-empty values, they are populated by an enrichment step we have not seen, or they came from a different ingestion that is out of scope.
- Connectors (`*_connector.ipynb`) have **no business logic** and need no Postgres/Python equivalent — replace with a simple CLI / cron entrypoint per pipeline (e.g., `python -m gains.ingest.schoology --workspace=prod --method=load_all`).
- All three frameworks rely on `oea._get_secret(<key>)` and `oea.land(...)` / `oea.load(...)` from the OEA helper. In the rebuild these become: secrets from env / Supabase vault, "land" = insert into a `raw_*` Postgres table or write to object storage, "load" = SELECT from that raw table.

---

## Appendix — Quick reference: methods to port

| Legacy method | New job/endpoint | Priority |
|---|---|---|
| `EdvanceLS.fetch_standard` + `load_standard` | `standards_sync` worker | P0 (Schoology depends on it) |
| `LMS.fetch_lmsData` + `lms_load_tables` | `edvance_lms_ingest` (only if Edvance dashboards in scope) | P2 |
| `LMS.lms_dimension_tables` / `lms_fact_tables` / `lms_aggregate_tables` | dbt models or Python transforms in `edvance_lms_marts` | P2 |
| `Schoology_py.*` | `schoology_ingest` + `schoology_marts` | P0 |
| `*_connector.ipynb` | CLI entrypoints with `--method` arg | trivial |
