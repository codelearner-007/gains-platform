# Schoology PySpark Notebook — Rebuild Spec

**Source:** `E:\Work\PS_P\gains\OEA\modules\module_catalog\Schoology_Analytics\notebook\Schoology_py.ipynb`
**Total lines:** 2525 (Jupyter JSON) — 4 cells; cell 4 (lines ~30–2491) is the `Schoology` class.
**Line numbers below are line offsets in the .ipynb file** (the notebook's `"source"` arrays preserve line breaks).

> Goal of this doc: capture every business rule needed to rebuild the pipeline on Postgres + dbt with **identical output schemas and identical formulas**. Formulas are quoted from the source.

---

## Section 1 — Class structure

### Signature & init (lines 46–51)

```python
class Schoology:
    def __init__(self, workspace='dev', version='0.1'):
        self.baseurl = "https://api.schoology.com/v1/"
        self.keyvault_consumer_key = f'schoologyConsumerKey{workspace}'
        self.keyvault_oauth_signature = f'schoologyOauthSignature{workspace}'
        self.version = version
```

The instance is constructed at line 2491: `schoology = Schoology()` (defaults: workspace='dev', version='0.1').

### Imports (lines 17–25)

```python
import datetime, json
from pyspark.sql import functions as F
from pyspark.sql.functions import col, avg, desc, first, asc, sum, when, substring, count,
    concat_ws, format_string, collect_list, last, round, monotonically_increasing_id,
    date_format, expr, regexp_replace, countDistinct, sha2, concat, col, split, expr,
    concat_ws, max
from scipy.stats import rankdata
from pyspark.sql.types import StringType
from pyspark.sql.window import Window
from pyspark.sql.functions import row_number, col
```

Cell 1 invokes `%run OEA_py` (line 8), which loads the OEA framework providing `oea.land()`, `oea.ingest()`, `oea.upsert()`, `oea.load()`, `oea.add_to_lake_db()`, `oea.to_url()`, `oea.fix_column_names()`, `oea.get_folders()`, `oea.path_exists()`, `oea.DELTA_BATCH_DATA`, etc.

### All methods on `Schoology`

| Line | Method | One-liner |
|------|--------|-----------|
| 47 | `__init__` | Set baseurl, keyvault key names, version |
| 53 | `set_workspace` | Forwards to `oea.set_workspace` |
| 56 | `set_version` | Updates `self.version` |
| 59 | `auth_header` | Builds Schoology PLAINTEXT OAuth1 header from KV secrets |
| 88 | `fetch_data` | Paginated GET via `links.next`, extracts `resultName` ('user' default) |
| 102 | `load_users` | Pulls active + inactive users from API; lands JSON to `schoology_raw/v{ver}/users` |
| 114 | `load_roles` | Pulls roles from API; lands JSON |
| 121 | `csv_files_list` | Recursively walks pre-landing path, collects `.csv` files |
| 135 | `get_files_from_bulk` | Calls `csv_files_list` then `preland_schoology_csv` per file |
| 144 | `preland_raw_folder` | Iterates folders under `oea/Raw_Files/Schoology` (skipping `Done_Prelanding`); moves processed folders into a dated `Done_Prelanding/{date}/` |
| 157 | `preprocess_schoology_dataset` | Reads JSON/CSV from `Stage1/Transactional/schoology_raw/{ver}/{item}/...`, splits `File_Path`, applies subject/teacher/grade overrides, writes to `schoology/v{ver}/{item}` (stage1) |
| 454 | `preland_batch_comp_files` | Reads a manifest text file of `folder,file` pairs, calls `preland_schoology_csv` per row |
| 469 | `preland_schoology_csv` | Pre-lands a CSV (Question-Data, Submission-Summary, Student-Submissions, Attendance, SIS) — fixes column names, melts wide → long for Standards / Answer_Breakdown / Question, builds `Unique_Key`, writes pandas CSV to stage1 |
| 627 | `process` | Spark structured streaming wrapper (`readStream` → `foreachBatch` → trigger-once) |
| 644 | `ingest_to_df` | Same shape as `oea.ingest`, but adds `delete_from_path` cleanup before upsert (used for `question_data` only) |
| 684 | `ingest_schoology_dataset` | Promotes stage1 → stage2/Ingested for each entity; PKs vary by entity |
| 711 | `refine_schoology_dataset` | No-op stub (TODO) |
| 729 | `delete_stale_rows` | For each `req_cols` triple, runs `delete_from_path` on stage2 + stage3 destinations |
| 736 | `delete_from_path` | Delta MERGE that deletes rows where `(req_cols[0], req_cols[1], req_cols[2])` exist in destination but no longer in source — soft-incremental cleanup |
| 769 | `_publish_to_stage2` | `oea.upsert(df, dest, pk)` |
| 771 | `_publish_to_stage3` | `oea.upsert(df, dest, pk)` |
| 774 | `publish` | Counts rows pre/post, calls both `_publish_to_stage2` + `_publish_to_stage3`, returns delta count |
| 798 | `build_dimension_tables` | Builds dim_school, dim_student, dim_teacher, dim_parent, dim_course, dim_item, dim_question_data, dim_standard, dim_strand, dim_unit_lesson, dim_section, dim_session, dim_grade, dim_assessment_type, dim_subject |
| 1180 | `build_fact_tables` | Builds `fact_student_submission` |
| 1295 | `build_pseudomyzed_tables` | Builds `dim_section_Hash` (TeacherName_Hash), `dim_student_hash` (StudentName_Hash), `fact_student_submissions_Hash` |
| 1322 | `cube_Build` | Calls `build_pseudomyzed_tables()` then builds 7 cubes (Grade, School, Standard, Question, QuestionIncorrectChoice, Question_Summary_Overall, OverallPerformance, User_Summary) |

---

## Section 2 — Helper functions

### UUID generators

These are **plain Python helpers (NOT registered as UDFs)** — they accept Column expressions and return Column expressions using `concat_ws` + `sha2(_, 256)`. Defined **twice**: in `build_dimension_tables` (lines 823–845) and again in `build_fact_tables` (lines 1203–1219) — identical logic.

```python
# line 823-826
def generate_uuid_2(column1, column2):
    combined_column = concat_ws("_", column1, column2)
    uuid = sha2(combined_column, 256)   # SHA-256 hex digest
    return uuid

# line 828-831
def generate_uuid_5(c1,c2,c3,c4,c5):
    combined_column = concat_ws("_", c1,c2,c3,c4,c5)
    return sha2(combined_column, 256)

# line 832-835
def generate_uuid_6(c1,c2,c3,c4,c5,c6):
    combined_column = concat_ws("_", c1,c2,c3,c4,c5,c6)
    return sha2(combined_column, 256)

# line 836-841 — note the BUG: concat_ws is overwritten by concat (no separator)
def generate_uuid_7(c1,c2,c3,c4,c5,c6,c7):
    combined_column = concat_ws("_", c1,c2,c3,c4,c5,c6,c7)
    combined_column = concat(c1,c2,c3,c4,c5,c6,c7)   # OVERWRITES previous line
    return sha2(combined_column, 256)

# line 842-845
def generate_uuid_8(c1,c2,c3,c4,c5,c6,c7,c8):
    combined_column = concat_ws("_", c1,c2,c3,c4,c5,c6,c7,c8)
    return sha2(combined_column, 256)
```

**Equivalent in Postgres:** `encode(digest(concat_ws('_', c1,c2,...), 'sha256'), 'hex')` (needs `pgcrypto`). For `generate_uuid_7`, drop the `_` separator: `encode(digest(c1||c2||c3||c4||c5||c6||c7, 'sha256'), 'hex')`.

### `fix_urls` (line 801)

```python
def fix_urls(question):
    pattern = r"http://app\.schoology\.com/system/files/.*?/(attachments/page_embeds)"
    replacement = r"http://app.schoology.com/system/files/\1"
    return re.sub(pattern, replacement, question)
fix_urls_udf = F.udf(fix_urls, StringType())   # this one IS registered
```

Applied to `df_Question.Question` (line 812).

### Other inline helpers

- **`replace_values(value, school_id)`** (line 402, inside `preprocess_schoology_dataset`) — looks up co-teacher pair → primary teacher name based on hardcoded `teacher_dict_athenian` (school 186370968), `teacher_dict_brightview` (7448280461), `teacher_dict_southprep` (7368546879). Registered as Spark UDF on line 422. **Hardcoded school IDs to flag.**
- **HTML cleanup**: `trim(regexp_replace(col("Question"), r"<[^>]*>", ""))` for `Question_no_url` (line 1727).
- **CR/LF cleanup**: `regexp_replace(df['description'], r'\r\n', ' ')` on the `standards` JSON description (line 191).
- **`pseudonymize`** function: **NOT FOUND** by that name. Pseudonymisation is implemented inline in `build_pseudomyzed_tables` using `monotonically_increasing_id()` to mint hashes like `Teacher_Name 0`, `Student_Name 0`, etc.

---

## Section 3 — Raw landing → ingestion

### Source paths

- **API**: `https://api.schoology.com/v1/users`, `/users/inactive`, `/roles` (lines 60–117). OAuth1 PLAINTEXT, secrets pulled from KV via `oea._get_secret(...)`.
- **Bulk CSV uploads**: `oea/Raw_Files/Schoology/{tenant_folder}/...` (line 145).
- **Pre-landing**: `oea/pre_landing/Schoology/...` (line 458).

### CSV read options (line 173)

```python
df = spark.read \
    .option("quote", "\"") \
    .option("escape", "\"") \
    .option("encoding", "UTF-8") \
    .option("multiLine", True) \
    .csv(..., header=True)
```

For pre-landing CSVs (line 474) the encoding is `ISO-8859-1`, plus `quoteAll=true`. Numeric/text columns `Question` and `Answer_Submission` get truncated to **7500 chars** with `SUBSTRING(Question, 1, 7500)` (lines 482–488).

### File-name routing (line 489 onward)

| Filename contains | `item` value |
|--|--|
| `Question-Data` | `question_data` |
| `Submission-Summary` | `submission_summary` |
| `Student-Submissions` | `student_submissions` |
| `Attendance` | `attendance` |
| `SIS` | `student_information` |

### Wide → long melts (in `preland_schoology_csv`, lines 489–598)

- **Question-Data:** melts all `Standards*` columns into (`Standards`, `Standards_Val`); then melts all `Answer_Breakdown*` columns into (`Answer_Breakdown`, `Answer_Breakdown_Val`). Keeps a row per question even when value is empty — *unless* another row for the same `Question_ID` already has a non-null `Standards_Val` (line 530). Adds `Question_No = scipy rankdata(Question_ID, method='dense')` (line 567). Builds `Unique_Key = Item_ID + Question_ID + Correct_Answer + Position_Number + Answer_Option + Answer_Breakdown + Standards` (line 558).
- **Submission-Summary:** melts all `Question*` columns. `Unique_Key = Schoology_ID + Question` (line 587).
- **Student-Submissions:** no melt. `Unique_Key = User_UID + Item_ID + Question_ID + Position_Number + Answer_Submission + Points_Received + Points_Possible + Submission + Correct_Answer` (line 593).

### Adding `File_Path` columns (line 569)

`df['File_Path'] = '/'.join(folderPath.split('/')[3:]) + fileName` — relative path from tenant root.

### Splitting `File_Path` to drive Session/Subject/Grade/Section (lines 218–227)

```python
split_cols = F.split(F.col("File_Path"), '/')
df = df.withColumn("Session",         split_cols.getItem(0)) \
       .withColumn("Assessment_type", assessment_type) \   # split[1] minus prefix before first '-'
       .withColumn("Subject",         F.trim(split_cols.getItem(2))) \
       .withColumn("Grade",           F.trim(split_cols.getItem(3))) \
       .withColumn("Section",         F.trim(split_cols.getItem(4))) \
       .withColumn("File_Name",       split_cols.getItem(5)) \
       .drop("File_Path")
```

`Assessment_type` is computed (line 219): if `split[1]` contains `-`, take everything **after the first `-`**; else trim `split[1]`.

### Tenant subject/grade overrides (lines 232–321)

Two API calls per (school_id, tenant_id) pair:

1. `https://api.edvancelearning.us/Reporting/api/app/tenant-config/tenant-config/{tenant_id}?key=SubjectOverrideConfigJson` — returns rules `{Grade, Subject, SubjectOverride}` applied as a chained `F.when(...)` (line 268).
2. `...?key=MapSubjectWithCourseNameJson` — adds `CourseNameMatchRegex` matched against `Course_Name` (line 308).

The legacy hardcoded versions of these mappings are still in commented form at lines 322–337, e.g. `(School_ID==186370968) & (Grade=='Grade 8') & (Subject=='Math') -> 'Algebra'`. **These are now dynamic via tenant config — but the old block reveals expected behaviour.**

### Deduplication / re-run safety

- **`delete_stale_rows`** (line 729) and **`delete_from_path`** (line 736): when re-ingesting, performs a **Delta MERGE WHEN MATCHED DELETE** for rows where the chosen `req_cols` triplet exists in the destination but is missing in the new source. Used for stage2 *and* stage3 to keep them in sync.
- **`ingest_to_df`** (line 644): used only for `question_data` — runs `delete_from_path` for two triplets (`['Item_ID','Question_ID','Standards_Val']` and `['Item_ID','Question_ID','Correct_Answer']`) before the Spark structured-streaming `foreachBatch` upsert.
- For the fact and cubes: `delete_stale_rows` is called with various triplets (see each section).
- A second-level dedupe in `build_fact_tables` line 1185:

  ```python
  key_columns = [c for c in df_Student_Submissions.columns
                 if c not in ("rundate","Unique_Key","Points_Received","Submission_Grade")]
  w = Window.partitionBy(key_columns).orderBy(F.col("rundate").desc())
  df = df.withColumn("rn", F.row_number().over(w)).filter("rn=1").drop("rn")
  ```

  → keeps the **latest `rundate` row** per (everything except points/grade). This handles re-runs of the same submission.

### `publish` method (line 774)

Reads existing stage2 (counts rows), upserts to stage2, upserts to stage3, reads new stage2 count, returns the delta. PK varies per call (passed in). Both stages use `oea.upsert` (Delta MERGE on PK).

---

## Section 4 — Dimension builds

All dims are built inside `build_dimension_tables` (line 798). Sources:

```python
df_User                 = oea.load('stage2/Ingested/schoology/v{ver}/users')
df_Question             = oea.load('stage2/Ingested/schoology/v{ver}/question_data')   # then fix_urls + Standards filter
df_Student_Submissions  = oea.load('stage2/Ingested/schoology/v{ver}/student_submissions')
df_Submission_Summary   = oea.load('stage2/Ingested/schoology/v{ver}/submission_summary')
```

`df_Student_Submissions` is renamed: `User_School_ID → School_ID`, `User_School_Name → School_Name` (line 847). `df_User` is renamed: `school_id → School_ID` (line 848).

### `dim_school` (line 851)

```python
df_dim_school = df_Student_Submissions[['School_ID','School_Name']] \
    .drop_duplicates() \
    .dropna(subset=['School_ID','School_Name'])
self.publish(..., primary_key='School_ID')
```

### `dim_student` (line 859)

```python
df_dim_student = df_User.filter(df_User['role_id'] == 286170)   # Student
df_dim_student = df_dim_student[['uid','id','School_ID','school_uid','name_title',
    'name_first','name_first_preferred','use_preferred_first_name','name_middle',
    'name_middle_show','name_last','name_display','primary_email','picture_url',
    'gender','position','grad_year','username','password','role_id','tz_offset',
    'tz_name','language']].drop_duplicates()
self.publish(..., primary_key='uid')
```

**Role IDs (verified):** Student = `286170`, Teacher = `286168` (line 875), Parent = `286172` (line 884).

### `dim_teacher` (line 875)

Same shape as dim_student except: filter `role_id == 286168`, **drops `school_uid`** (no school_uid for teachers in Schoology), keeps the rest of the column list.

### `dim_parent` (line 884)

Filter `role_id == 286172`. Adds `child_uids` to the column list.

### `dim_course` (line 899)

```python
df_dim_course = df_Student_Submissions[['Course_NID','Course_Name','Course_code','School_ID']] \
    .drop_duplicates().dropna(subset=['Course_NID','Course_Name','Course_code','School_ID'])
self.publish(..., primary_key='Course_NID')
```

### `dim_item` (line 925)

Built **after** the synthetic `Subject_ID/Grade_ID/Assessment_ID` columns are added to a working copy of student_submissions (lines 904–924).

```python
df_Student_Submissions = df_Student_Submissions.withColumn("User_id_ques_id",
    concat(col("User_UID"), lit('-'), col("Question_ID")))
df_Student_Submissions = df_Student_Submissions.withColumn('Qkey',
    concat(col('Session'), col('Assessment_type'), col('Subject'), col('Grade'), col('Question_ID')))

fact_Student_Submissions = ... .withColumn("assessment_date", date_format(col("Latest_Attempt"), "MM/dd/yyyy"))
fact_Student_Submissions = fact_Student_Submissions.withColumn("Grade_ID",
    generate_uuid_2(df['School_ID'], df['Grade']))
fact_Student_Submissions = fact_Student_Submissions.withColumn("Assessment_ID",
    generate_uuid_2(df['School_ID'], df['Assessment_type']))
fact_Student_Submissions = fact_Student_Submissions.withColumn("Subject_ID",
    generate_uuid_6(df['School_ID'], df['Subject'], df['Assessment_type'],
                    df['Grade'], df['Session'], df['Item_Name']))
```

Then `dim_item`:

```python
df_dim_item = fact_Student_Submissions[['Item_ID','Subject_ID','assessment_date',
    'Section_Name','Section_Instructors','Item_Type','Item_Name','School_ID']].drop_duplicates() \
    .dropna(subset=[...])
# keep first occurrence per Item_ID/Subject_ID/Section_*/Item_*/School_ID by earliest assessment_date
window_spec = Window.partitionBy('Item_ID','Subject_ID','Section_Name','Section_Instructors',
    'Item_Type','Item_Name','School_ID').orderBy(col('assessment_date').asc())
df_dim_item = df_dim_item.withColumn('row_num', row_number().over(window_spec)) \
                         .filter(col('row_num')==1).drop('row_num')
self.publish(..., primary_key='Item_ID')
```

### `dim_question_data` (line 945)

```python
# join Item->School from dim_item
df_Student_Submissions = oea.load('stage3/Published/schoology/v{ver}/dim_item')
df_Student_Submissions_schoolID = df_Student_Submissions.select("Item_ID","School_ID")
df_Question_schoolID = df_Question.join(df_Student_Submissions_schoolID, on=["Item_ID"], how="left")

# rename Standards_Val -> Standard, drop original Standards
df_Question_schoolID = df_Question_schoolID.drop("Standards") \
    .withColumnRenamed('Standards_Val','Standard')

df_dim_question_data = df_Question_schoolID[[
    'Question','Position_Number','Item_ID','Item_Name','School_ID','Standard',
    'Question_ID','Question_No','Least_Points_Earned','Correct_Answer',
    'Question_Type','Average_Points_Earned','Associated_Question_ID',
    'Total_Points','Most_Points_Earned','Correctly_Answered',
    'Sub-Question','Session','Assessment_type','Subject','Grade','Section'
]].drop_duplicates()

# Grade 9-12 remap for school 554425139
df_dim_question_data = df_dim_question_data.withColumn("Grade",
    F.when((F.col("School_ID") == "554425139") &
           (F.col("Grade").isin(["Grade 9","Grade 10","Grade 11","Grade 12"])),
           "Regular 9–12")
    .otherwise(F.col("Grade")))
```

Then joins `dim_standard` (lines 988–993):

```python
standard = oea.load('stage3/Published/schoology/v{ver}/dim_standard') \
    .withColumnRenamed("Schoology_Standard","Standards")
dim_standard = standard[['Identifier','Standards']]
df_dim_question_data = df_dim_question_data.join(
    dim_standard,
    df_dim_question_data.Standard.contains(dim_standard.Standards),  # substring match!
    how="left")
```

Builds two synthetic keys (lines 996–1018):

```python
Qkey = concat(<Session or 'DEFAULT_SESSION'>, <Assessment_type ...>, <Subject>, <Grade>,
              <Question_ID>, <Position_Number>, <Correct_Answer>, <Standard>, <School_ID>)
Ukey = generate_uuid_8(School_ID, Session, Assessment_type, Item_Name,
                       Subject, Grade, Question, Correct_Answer)
```

Calls `delete_stale_rows` with two triplets `(School_ID, Question_ID, Standard)` and `(School_ID, Question_ID, Correct_Answer)` then `publish(... primary_key='Qkey')` (line 1028).

### `dim_standard` build (line 1031)

Source: `oea.load('stage2/Ingested/schoology/v{ver}/standards')` (this is the JSON-ingested Schoology Standards API output).

After ingesting, builds `dim_standard` by joining standards table to `dim_question_data` two ways and unioning:

```python
df_dim_question_data1 = question_data.join(
    standard,
    question_data.Standard.contains(standard.Schoology_Standard), how="left")[
    "Cognitive_Complexity_Rating","Direct_Link","Grader","Identifier","Language",
    "Standard","Standard_New","Strand","Subject","cluster","description",
    "lastChangeDateTime","rundate"
].dropDuplicates([...])

df_dim_question_data = standard.join(
    question_data,
    standard.Schoology_Standard.contains(question_data.Standard), how="left")[same_cols]
.dropDuplicates([...])

df_dim_question_data = df_dim_question_data.union(df_dim_question_data1)
dim_strand = ...same selection...
dim_strand = dim_strand.withColumnRenamed('Standard','Schoology_Standard')
dim_strand = dim_strand.union(df_dim_standard[same_cols]).na.drop()
dim_strand = dim_strand.filter(~col("Schoology_Standard").rlike(r"^\d+$"))   # drop pure-numeric rows
dim_strand = dim_strand.dropDuplicates(["Schoology_Standard"])
dim_strand = dim_strand.withColumn("cPalms_Standard",
    F.expr("concat_ws('.', slice(split(Schoology_Standard, '\\\\.'), 3, size(split(Schoology_Standard, '\\\\.'))))"))
dim_strand = dim_strand.withColumn("uniquesID",
    when((col("Identifier")=="Other") | (col("Schoology_Standard")=="Other"), "Other")
    .otherwise(concat_ws("_", col("Identifier"), col("Schoology_Standard"))))
schoology.publish(dim_strand, ..., primary_key='uniquesID')
```

This dataframe is **persisted as `dim_standard`** (line 1097) — confusing naming but verified.

### `dim_strand` build (line 1102)

```python
question_data = oea.load('stage3/Published/schoology/v{ver}/dim_question_data').drop("Identifier")
standard      = oea.load('stage3/Published/schoology/v{ver}/dim_standard')
df_dim_question_data = standard.join(
    question_data,
    standard.Schoology_Standard.contains(question_data.Standard),
    how="left")
dim_strand = df_dim_question_data[["Identifier","Strand"]].dropDuplicates(["Identifier","Strand"])
dim_strand = dim_strand.withColumn("ID", monotonically_increasing_id())
dim_strand = dim_strand.withColumn("strand_ID", generate_uuid_2(dim_strand['Identifier'], dim_strand['Strand']))
schoology.publish(dim_strand, ..., primary_key='ID')
```

**Final shape: `(Identifier, Strand, ID, strand_ID)`** — `ID` is the publish PK (Spark `monotonically_increasing_id`); `strand_ID` is the SHA-256 of `Identifier_Strand` and is the join key downstream.

### Other dims (lines 1135–1176)

```python
# dim_unit_lesson  (PK: Item_ID)
dim_unit_lesson = df_Student_Submissions[['Item_ID','Item_Name','School_ID']].drop_duplicates()

# dim_section  (PK: Section_NID)
df_dim_section = fact_Student_Submissions[['Section_Code','Item_ID','Section_NID',
    'Section_Name','Section_Instructors','School_ID']].drop_duplicates() \
    .dropna(subset=[...])

# dim_session  (PK: Session_ID)
dim_session = fact_Student_Submissions[['School_ID','Session']].drop_duplicates()
dim_session = dim_session.withColumn("session_ID",
    generate_uuid_2(dim_session['School_ID'], dim_session['Session']))
dim_session = dim_session.dropna(subset=["Session_ID","School_ID","Session"])

# dim_grade  (PK: Grade_ID)
dim_grade = fact_Student_Submissions[['Grade_ID','School_ID','Grade']].drop_duplicates() \
    .dropna(...)

# dim_assessment_type  (PK: Assessment_ID)
dim_assessment_type = fact_Student_Submissions[['Assessment_ID','School_ID','Assessment_type']]
    .drop_duplicates().dropna(...)

# dim_subject  (PK: Subject_ID)
dim_subject = fact_Student_Submissions[['Subject_ID','School_ID','Subject',
    'Assessment_type','Grade','Session','Item_Name']].drop_duplicates().dropna(...)
```

---

## Section 5 — Fact build (`fact_student_submission`, line 1180)

### Source dedupe (line 1184–1192)

Latest-rundate window dedupe described in §3.

### Filter on Question (line 1199)

```python
df_Question = oea.load('stage2/Ingested/schoology/v{ver}/question_data')
df_Question = df_Question.filter(
    (F.col('Standards_Val').isNull()) & (F.col('Standards') != 'Standards17')
    | (F.col('Standards').isNull() & F.col('Standards_Val').isNull()))
```

Only used for join on Standard via `dim_question_data` later.

### Column projection (line 1224)

```python
df_Student_Submissions = df_Student_Submissions[['User_UID','First_Name','Last_Name',
    'User_Role_ID','School_ID','Course_NID','Section_NID','Section_Code','Item_ID',
    'Item_Name','First_Access','Latest_Attempt','Total_Time','Submission_Grade',
    'Submission','Question_ID','Session','Assessment_type','Subject','Grade','Section',
    'File_Name','Position_Number','Sub-Question','Answer_Submission','Correct_Answer',
    'Points_Received','Points_Possible']]
```

### Computed columns (lines 1230–1246)

```python
User_id_ques_id = concat(User_UID, '-', Question_ID)
User_Name       = concat(First_Name, ' ', Last_Name)
Qkey            = concat(Session, Assessment_type, Subject, Grade, Question_ID)
Grade_ID        = generate_uuid_2(School_ID, Grade)                # SHA-256(School_ID_Grade)
Assessment_ID   = generate_uuid_2(School_ID, Assessment_type)
Subject_ID      = generate_uuid_6(School_ID, Subject, Assessment_type, Grade, Session, Item_Name)
```

### Joins (lines 1255–1268)

```python
# join question -> standard string (needed for Identifier)
ques_stand = questiondata[["Question_ID","Standard"]].dropDuplicates()
fact = fact.join(ques_stand, on=["Question_ID"], how="left")
# join Standard -> Identifier via dim_standard (Schoology_Standard renamed)
fact = fact.join(dim_standard[['Identifier','Standard']], on=["Standard"], how="left")
# join Identifier -> strand_ID via dim_strand
fact = fact.join(dim_strand[['Identifier','strand_ID']], on=["Identifier"], how="left")
```

### Synthetic PK `User_id_ques_id_stand` (line 1270)

```python
User_id_ques_id_stand = concat(
    coalesce(School_ID, 'DEFAULT_SCHOOLID'),    '-',
    coalesce(User_UID, 'DEFAULT_USER'),         '-',
    coalesce(Question_ID, 'DEFAULT_QID'),       '-',
    coalesce(Position_Number, 'DEFAULT_POS'),   '-',
    coalesce(Answer_Submission, 'DEFAULT_ANSWER_SUBMISSION'), '-',
    coalesce(Points_Possible, 'DEFAULT_POINTS_REC'),         '-',
    coalesce(Submission, 'Submission'),         '-',
    coalesce(Standard, 'DEFAULT_STANDARD'))
```

### Final published columns (after joins)

`User_UID, User_Name, User_Role_ID, School_ID, Course_NID, Section_NID, Section_Code, Item_ID, Item_Name, First_Access, Latest_Attempt, Total_Time, Submission_Grade, Submission, Question_ID, Session, Assessment_type, Subject, Grade, Section, File_Name, Position_Number, Sub-Question, Answer_Submission, Correct_Answer, Points_Received, Points_Possible, User_id_ques_id, Grade_ID, Assessment_ID, Subject_ID, Standard, Identifier, strand_ID, User_id_ques_id_stand`

`delete_stale_rows` triplet: `[School_ID, Question_ID, Standard]`. Publish PK: `User_id_ques_id_stand` (line 1292).

---

## Section 6 — Standards & strand details

- **Standards source:** Schoology `/standards` API → JSON → `stage1/Transactional/schoology_raw/v{ver}/standards/{batch}/rundate=...` (line 117). Pre-process casts `links` to string and replaces `\r\n` in description (line 191). Ingestion uses PK `Identifier` (line 698).
- **Schema columns** (inferred from references): `Cognitive_Complexity_Rating, Direct_Link, Grader, Identifier, Language, Schoology_Standard, Standard_New, Strand, Subject, cluster, description, lastChangeDateTime, rundate`.
- **`Trimmed_Standard`/cPalms** — `cPalms_Standard` is built (line 1085) from `Schoology_Standard`:
  ```python
  concat_ws('.', slice(split(Schoology_Standard, '\.'), 3, size(split(Schoology_Standard, '\.'))))
  ```
  i.e., drop the first two dot-segments. Example: `SCI.5.SC.5.P.13.1` → `SC.5.P.13.1`.
- **HTML cleanup of `description`** — only the `\r\n` → space replacement (line 191). No `<tag>` stripping on description.
- **`Question_no_url`** — used in `Cube_Question_Summary` (line 1727) and `Cube_Question_Summary_Overall` (line 2125): `trim(regexp_replace(Question, r"<[^>]*>", ""))` — HTML tags stripped from `Question` body.
- **No explicit cross-join between dim_strand and Cube_Question_Summary_Overall** is performed; instead `Cube_Question_Summary_Overall` joins `dim_standard` on substring match (line 2153) for `Description`.

---

## Section 7 — Cube builds

`cube_Build` (line 1322) calls `build_pseudomyzed_tables()` first, then computes Total_Seconds:

```python
# line 1330
Total_Seconds = int(split(Total_Time, ':')[0])*3600
              + int(split(Total_Time, ':')[1])*60
              + int(split(Total_Time, ':')[2])
```

Then `Standard` is renamed to `Standards` (line 1335).

### Pseudonymisation tables (line 1295–1320)

```python
# dim_section_Hash  (PK: Section_NID)
fact_student_submissions_Unique = fact_join_dim_item.groupby("Section_NID","Section_Instructors")
    .agg(sum("Item_ID"))
    .select("Section_NID","Section_Instructors")
    .withColumn("TeacherName_Hash", concat(F.lit("Teacher_Name "), monotonically_increasing_id()))

# dim_student_hash  (PK: User_UID)
fact_student_submissions_Unique = fact.groupby("User_UID","User_Name").agg(sum("Item_ID"))
    .select("User_UID","User_Name")
    .withColumn("StudentName_Hash", concat(F.lit("Student_Name "), monotonically_increasing_id()))

# fact_student_submissions_Hash  (PK: User_id_ques_id_stand)
# = fact_student_submission left-joined to dim_student_hash on User_UID
```

### `Cube_Grade_Summary` (line 1337, PK `ID`)

```python
Cube_Grade_measure = Fact.groupby('School_ID','Subject_ID','User_UID','Item_ID').agg(
    (sum("Points_Received") / sum("Points_Possible")).alias("Grade_Average"))
Cube_Grade_Summary = Cube_Grade_measure.rollup('School_ID','Subject_ID','Item_ID').agg(
    avg("Grade_Average").alias("Grade_Average"),
    (1 - avg(F.col('Grade_Average'))).alias("Percentage_InCorrect_Answers"),
    F.min("Grade_Average").alias("Grade_Min"),
    F.max("Grade_Average").alias("Grade_Max"))
ID = sha2(concat(coalesce(School_ID,'DEFAULT_SCHOOL_ID'),
                 coalesce(Subject_ID,'DEFAULT_SUBJECT_ID'),
                 coalesce(Item_ID,'DEFAULT_ITEM_ID')), 256)
```

**dbt skeleton:**
```sql
WITH per_user AS (
  SELECT School_ID, Subject_ID, User_UID, Item_ID,
         SUM(Points_Received)::numeric / NULLIF(SUM(Points_Possible),0) AS Grade_Average
  FROM fact_student_submission GROUP BY 1,2,3,4),
rolled AS (
  SELECT School_ID, Subject_ID, Item_ID,
         AVG(Grade_Average) AS Grade_Average,
         1 - AVG(Grade_Average) AS Percentage_InCorrect_Answers,
         MIN(Grade_Average) AS Grade_Min,
         MAX(Grade_Average) AS Grade_Max
  FROM per_user GROUP BY GROUPING SETS ((School_ID,Subject_ID,Item_ID),
                                        (School_ID,Subject_ID),(School_ID),()))
SELECT *, encode(digest(coalesce(School_ID,'DEFAULT_SCHOOL_ID')||
                        coalesce(Subject_ID,'DEFAULT_SUBJECT_ID')||
                        coalesce(Item_ID,'DEFAULT_ITEM_ID'),'sha256'),'hex') AS id
FROM rolled;
```

### `Cube_School_Summary` (line 1367, PK `ID`)

```python
Cube_School_Summary = Fact.rollup('School_ID','Subject_ID','Item_ID').agg(
    countDistinct("Question_ID").alias("Total_Questions"),
    countDistinct("Identifier").alias("Total_Standards"),
    countDistinct("User_UID").alias("Total_Students"),
    sum("Points_Possible").alias("Total_Possible_Point"),
    sum("Points_Received").alias("Total_Score"),
    (sum("Points_Received") / sum("Points_Possible")).alias("Grade_Average"),
    (1 - sum(F.col('Points_Received'))/sum(F.col('Points_Possible')))
        .alias("Percentage_InCorrect_Answers"))
ID = sha2(concat(coalesce(School_ID,..),coalesce(Subject_ID,..),coalesce(Item_ID,..)),256)
```

### `Cube_Standard_Summary` (line 1392, PK `ID`)

```python
rollup('Item_ID','Strand_ID','Identifier').agg(
    countDistinct("Question_ID")  -> Total_Questions,
    countDistinct("Identifier")   -> Total_Standards,
    sum("Points_Possible")        -> Total_Possible_Point,
    sum("Points_Received")        -> Total_Score,
    sum/sum                       -> Grade_Average,
    1 - sum/sum                   -> Percentage_InCorrect_Answers)
ID = sha2(concat(coalesce(Item_ID,...),coalesce(Strand_ID,...),coalesce(Identifier,...)),256)
```

### `Cube_Question_Summary` (line 1581 onward, PK `ID`)

Two-stage build: first the totals per `(Item_ID, Question_ID)`, then a separate **incorrect-choice analysis** is joined back.

**Totals:**
```python
Cube_Question_Summary = Fact.groupBy('Item_ID','Question_ID').agg(
    sum("Points_Possible") -> Total_Possible_Point,
    sum("Points_Received") -> Total_Score,
    Grade_Average, Percentage_InCorrect_Answers)
```

**Incorrect choice analysis (lines 1593–1689):**
- `ChoiceSubmissions` = dropDuplicates over `(Question_ID, Answer_Submission, Position_Number, Points_Received, User_Name, StudentName_Hash)`.
- `TotalSubmissions` = `count(Answer_Submission)` per `(Question_ID, Position_Number)`.
- `Choice_Submission_Count` = `sum(case when Points_Received < Points_Possible then 1 else 0 end)` per `(Question_ID, Position_Number, Answer_Submission)` (line 1606).
- `Choice_Percentage = Choice_Submission_Count / Total_Submissions` (line 1611).
- `Is_Correct = case when Points_Received < Max_marks then 'Incorrect' else 'Correct' end`.
- For each Incorrect choice: collect the lists of `User_Name` and `StudentName_Hash` who chose it. Build `Choice_Details` (with %), `Choice_Details_Hash` (same with hashed names), `Choice_Details_WithName`, `Choice_Details_WithName_Hash`. All truncated to 7500 chars.
- `ChoicesPerQuestion` aggregates `concat_ws(", ", collect_list(...))` per `(Question_ID, Position_Number)`.
- Then joined back to `Cube_Question_Summary` via `posNoQues = DimQuestionData.select("Question_ID","Item_ID","Position_Number")`, then to `DimQuestionData` and `DimItemName`, plus a `dim_section_Hash` join for `TeacherName_Hash`.
- `Question_no_url = trim(regexp_replace(Question, r"<[^>]*>", ""))`.
- Null `Standard`/`Standards` → `'Other'`.
- ID hash = `sha2(concat(School_ID, Item_ID, Item_Name, Question_ID, Position_Number, Standard, Correct_Answer), 256)`.
- `delete_stale_rows` triplets: `(School_ID, Question_ID, Standard)` and `(School_ID, Question_ID, Correct_Answer)`.

### `Cube_QuestionIncorrectChoice_Summary` (line 1772, PK `ID`)

```python
Fact.join(DimQuestionData, on=["Question_ID","Position_Number"], how="left")
   .rollup('Question_ID','UKey','Answer_Submission').agg(
        countDistinct("User_UID")    -> Total_Student,
        sum("Points_Possible")       -> Total_Possible_Point,
        sum("Points_Received")       -> Total_Score,
        Grade_Average, Percentage_InCorrect_Answers)
ID = sha2(concat(UKey, Question_ID, Answer_Submission),256)
```

### `Cube_Question_Summary_Overall` (line 1953 onward, PK `ID`)

Note: a long commented-out version exists earlier (lines 1799–1949). The active version starts at line 1953.

- Top-N filter: window-pick latest `(Submission desc, Total_Seconds desc)` per `(Section_NID,Session,Grade,Subject,Assessment_type,School_ID,User_UID,Item_ID,Question_ID)` (line 2245).
- `fillna({'Correct_Answer':'n/a'})` (line 1965).
- Joins `dim_subject` on `Subject_ID`, then `dim_question_data` on `(Question_ID, Item_ID, Item_Name, Position_Number)` (line 1996).
- Group by `('uKey','Subject_ID','Question_No','Question','Position_Number','Correct_Answer','Standard')`:
  - `Total_Possible_Point = sum(Points_Possible)`
  - `Total_Score = sum(Points_Received)`
  - `Grade_Average = sum(Points_Received)/sum(Points_Possible)`
  - `Percentage_InCorrect_Answers = 1 - that`
- Then attaches incorrect-choice details (same shape as Cube_Question_Summary) per `(uKey,Subject_ID,Question_No,Question,Position_Number,Correct_Answer,Standard)`.
- Joins `dim_standard` on `Standards.contains(Schoology_Standard)` for `Description` (line 2153).
- Joins `dim_item` on `Subject_ID` for `Section_Instructors`, then `dim_section_Hash` for `TeacherName_Hash`.
- `Question_no_url = trim(regexp_replace(Question, r"<[^>]*>", ""))`.
- Null `Standards` → `'Other'`.
- `ID = sha2(concat_ws(", ", Subject_ID, Question_No, Position_Number, Correct_Answer, Standards, Standards_for_uKey_branch), 256)` (line 2168). **NB the branch on line 2173 has a bug — when `uKey` is non-null it uses `Standards` again, not `uKey`.**

### `Cube_OverallPerformance_Summary` (line 2192, PK `ID`)

```python
Cube_OverallPerformance_Summary = Fact_with_Dim.groupby(
    'Identifier','Item_ID','Item_Name','Question_ID','Question_No','Standards').agg(
    sum("Points_Possible") -> Total_Possible_Point,
    sum("Points_Received") -> Total_Score,
    Grade_Average, Percentage_InCorrect_Answers)
ID = sha2(concat_ws(", ", Identifier, Item_ID, Item_Name, Question_ID, Question_No, Standards), 256)
```

`delete_stale_rows` triplet: `[Item_ID, Question_ID, Standards]` (line 2271).

### `Cube_User_Summary` (line 2278, PK `ID`)

This is the largest cube. It builds **6 intermediate aggregates** then assembles them.

1. `Cube_User_Question_Summary` per `(Section_NID,Section_Instructors,Session,Grade,Subject,Assessment_type,User_UID,User_Name,Item_ID,Item_Name,School_ID)`:
   - `Max_Total_Possible_Point_By_Question = round(sum(Total_Points),2)` (Total_Points comes from question_data after join)
   - `Total_Score_By_Question = round(sum(Points_Received),2)`
2. `max_values` = `MAX(Max_Total_Possible_Point_By_Question)` per `(Section_NID,..., Item_ID, Item_Name, School_ID)` → `Total_Possible_Point_By_Question`.
3. `Cube_User_Overall_Summary` per `(Session, Grade, Subject, Assessment_type, Item_Name, School_ID)`: `sum(Total_Possible_Point_By_Question)` → `Total_Possible_Point_By_Overall`; `sum(Total_Score_By_Question)` → `Total_Score_By_Overall`.
4. `Cube_User_OverallYear_Summary` per `(Session, Grade, Subject, Assessment_type, School_ID)`: similar but year-wide.
5. `Cube_UserCount_Item_Summary`: `countDistinct(User_UID)` per item → `countStudent`.
6. `Cube_User_Item_Summary`: `Total_Score_By_Item = round(sum(Points_Received),2)`; `Max_Possible_Point_By_Item = max(Total_Points)`; then `Total_Possible_Point_By_Item = countStudent * Max_Possible_Point_By_Item`.
7. `Cube_User_Standard_Summary`: `round(sum(Total_Points),2)` and `round(sum(Points_Received),2)` per `(Session, Grade, Subject, Assessment_type, Item_Name, Standards_ques, School_ID)`.
8. `Cube_User_Section_Summary` per `(Section_NID, Section_Instructors, Session, Grade, Subject, Assessment_type, Item_ID, Item_Name, School_ID)`: sums of question-level points/scores.
9. `Cube_User_Summary` (the final base) per `(Section_NID, Section_Instructors, Session, Grade, Subject, Assessment_type, User_UID, User_Name, Item_ID, Item_Name, Question_ID, Question_No, Standards_ques, School_ID)`: `Total_Possible_Point = round(sum(Total_Points),2)`, `Total_Score = round(sum(Points_Received),2)`.
10. Joined to ALL aggregates above; plus `Cube_User_SummaryUserPossiblePoint` (per-student grand total) and `Cube_User_SummaryUseroverallPossiblePoint` (per-section/year grand total).
11. Joins `dim_student_hash` (StudentName_Hash) and `dim_section_Hash` (TeacherName_Hash).
12. `ID = sha2(concat_ws(', ', Section_NID, Session, Grade, Subject, Assessment_type, User_UID, User_Name, Item_ID, Item_Name, Question_ID, Question_No, Standards_ques, School_ID), 256)`.
13. `Standards_ques` renamed back to `Standards`.
14. `delete_stale_rows` triplet: `[School_ID, Question_ID, Standards]`.

### Order of cube_Build (line 1322)

1. `build_pseudomyzed_tables()` (creates dim_section_Hash, dim_student_hash, fact_student_submissions_Hash)
2. `Cube_Grade_Summary`
3. `Cube_School_Summary`
4. `Cube_Standard_Summary`
5. `Cube_Question_Summary` (with incorrect-choice details)
6. `Cube_QuestionIncorrectChoice_Summary`
7. `Cube_Question_Summary_Overall`
8. `Cube_OverallPerformance_Summary`
9. `Cube_User_Summary` (and `Cube_User_Summary_Paginated` is incomplete in the source — the partition spec is set but the dbt-relevant grouping is the standard one above)

---

## Section 8 — Special transformations

- **`dim_question_data` Standard ↔ Standards substring join** (line 989): `df_dim_question_data.Standard.contains(dim_standard.Standards)` — meaning `Standard` (long form) string-contains the short `Standards` code. Postgres equivalent: `q.Standard LIKE '%' || s.Standards || '%'`.
- **Grade 9-12 → "Regular 9–12" remap** (line 985, also commented at line 336): `(School_ID == "554425139") AND (Grade IN ['Grade 9','Grade 10','Grade 11','Grade 12'])` → `'Regular 9–12'`. Note the **en-dash `–`**, not a hyphen. **Hardcoded to school 554425139 — needs parameterisation.**
- **`withColumnRenamed` calls of note:**
  - `User_School_ID → School_ID`, `User_School_Name → School_Name` (lines 847, 1222)
  - `school_id → School_ID` (line 848)
  - `Standards_Val → Standard` (line 949)
  - `Schoology_Standard → Standards` (line 990) and back (line 1259)
  - `Standard → Standards` (lines 1335, 1577, 2025) and back at line 2138
  - `Standards → Standards_ques` (line 2284, 2347) and back at line 2476
- **`na.drop` / `dropna` / `fillna`:** Most dim builds dropna on the visible PKs. `fillna({'Correct_Answer':'n/a'})` at line 1965, `fillna({'Standard':'null'})` at line 1968, etc. `Standards.isNull() | Standards == 'null' → 'Other'` is applied late to several cubes.
- **Regex operations:**
  - `regexp_replace(description, r'\r\n', ' ')` for standards (line 191).
  - `dim_strand.filter(~col("Schoology_Standard").rlike(r"^\d+$"))` drops pure-digit standards (line 1083).
  - `regexp_replace(Question, r"<[^>]*>", "")` for `Question_no_url` (lines 1727, 2125).
- **`Question_no_url` derivation** = trimmed HTML-stripped version of `Question` field.
- **Total_Time → Total_Seconds** (lines 1330, 1574, 1955, 2197, 2243): `int(split(t,':')[0])*3600 + int(split(t,':')[1])*60 + int(split(t,':')[2])`.

---

## Section 9 — Things to flag for our rebuild

1. **Hardcoded school_id values:**
   - `186370968` (Athenian) — co-teacher dict
   - `7448280461` (Brightview) — co-teacher dict
   - `7368546879` (SouthPrep) — co-teacher dict
   - `554425139` (Grade 9-12 → Regular 9–12 remap)
   These must be moved to a config table.
2. **Hardcoded co-teacher → primary teacher dictionaries** at lines 367–401 (Athenian), 401–410 (Brightview), 411–413 (SouthPrep). Should become a seed table `teacher_pair_overrides(school_id, pair, primary)`.
3. **Tenant-config API calls** (lines 246, 287) at `https://api.edvancelearning.us/Reporting/api/app/tenant-config/...` — these are external and **need a Postgres-side replacement** (config table or daily sync).
4. **Role IDs hardcoded:** Student=286170, Teacher=286168, Parent=286172. Consider a `role_lookup(role_id, role_name)` table.
5. **Timezone:** `tz_offset`/`tz_name` are stored on user records but no global TZ is applied in calcs. Dates use `date_format("MM/dd/yyyy")` (line 921) — string output, not timestamp; assume **Eastern** based on dataset origin but **NOT FOUND IN NOTEBOOK** as an explicit setting.
6. **Refresh order dependencies (critical):**
   - dim_school, dim_student, dim_teacher, dim_parent, dim_course, then dim_item (depends on synthetic Subject_ID)
   - dim_question_data **requires** dim_item (Item_ID→School_ID) and dim_standard (substring join)
   - dim_standard **requires** dim_question_data (joined back)
   - dim_strand **requires** dim_standard
   - **There is a circular dependency dim_standard ↔ dim_question_data**: `dim_question_data` is published first using a stale `dim_standard`, then `dim_standard` is rebuilt from the fresh `dim_question_data`, then `dim_strand` is built from both. The current notebook resolves this by reading prior runs' stage3 versions for the join — **first-time runs may have nulls**.
   - fact_student_submission requires dim_question_data, dim_standard, dim_strand
   - All cubes depend on fact_student_submission + dim_question_data + dim_item + dim_subject + dim_section_Hash + dim_student_hash
7. **Incremental vs full refresh:** Pipeline is **incremental** at the Delta layer via `delete_stale_rows` + `oea.upsert` (Delta MERGE on PK). For our rebuild, plan dbt incremental models with explicit `unique_key` matching the PKs above and `merge` strategy.
8. **`generate_uuid_7` bug** (line 840) — `concat_ws` is overwritten by `concat` (no separator). If any downstream code calls `generate_uuid_7` we must reproduce this exactly. *Search shows it is defined but I see no call site* — apparently dead code.
9. **Cube_Question_Summary_Overall ID hash bug** (line 2173) — references `Standards` twice instead of `uKey` once. Reproduce this bug if matching old hash IDs is a requirement; otherwise fix it.
10. **Cube `Total_Possible_Point` formula in user-cubes** (lines 2223, 2369) is `Ass_Total_Points = countDistinct(Question_ID)` — this is **the count of distinct questions**, not a sum of `Points_Possible`. The PowerBI model probably expects this. Verify against PBIX schema.
11. **CSV truncation** to 7500 chars on `Question`, `Answer_Submission` (lines 482–488) and on `Incorrect_Choice_Details*` columns (lines 1681, 2110). Postgres TEXT can hold more, but match if downstream PBIX expects it.
12. **Pandas `melt` operations** in `preland_schoology_csv` for Question-Data and Submission-Summary — these reshape wide-table CSVs into long format. Postgres equivalent: `UNPIVOT` or `LATERAL` over an array of column names.

---

## Section 10 — Open questions

1. **Standards source data:** Is the Schoology Standards JSON shipped as files or pulled live via API on every run? The code path `oea.ingest('schoology/v{ver}/standards','Identifier')` (line 698) suggests file-based, but `load_users`/`load_roles` use API. **Confirm Standards loading mechanism.**
2. **`dim_role` table:** The comment block at line 855 mentions a `Dim_Role` with `Role_ID`/`Role_Name` but it is not built. **Do we need it for the dbt rebuild, or is the role_id column on dim_student/dim_teacher/dim_parent enough?**
3. **`student_information` and `attendance` tables:** Pre-processed and ingested with PK `Student_ID` (line 696) but never joined into any dim or cube downstream. **Confirm whether these feed any non-Schoology pipeline or are vestigial.**
4. **`session_ID` casing:** dim_session writes `session_ID` (line 1153) but `publish` PK is `'Session_ID'` (line 1155). Check whether the upsert layer is case-insensitive.
5. **`Cube_Question_Summary` vs `Cube_Question_Summary_` (with trailing underscore):** A first version writing to `Cube_Question_Summary_` is fully commented out (lines 1417–1559). The active version writes to `Cube_Question_Summary`. **No conflict — but worth noting if older PBIX measures reference the legacy table.**
6. **`Cube_User_Summary_Paginated`:** Lines 2287–2483 set up a paginated variant but it ends up writing to the same `Cube_User_Summary` path. **Is the paginated build dead code or is the published Cube_User_Summary actually the result of step 11 above? Tracing shows the latter.**
7. **`generate_uuid_7` bug** — confirm whether to preserve or fix.
8. **`Cube_Question_Summary_Overall.ID` hash** — confirm whether to preserve the bug.
9. **`Standard.contains(Standards)`** substring join (lines 989, 1063): some Schoology codes are prefixes of others (e.g., `MA.7.DP.2` is a prefix of `MA.7.DP.2.1`). This will produce **multiple matches per question**. The `dropDuplicates` on `Identifier`/`Standard` rows mitigates it but **needs a unit test** in the Postgres rebuild.
10. **`dim_standard` dual identity:** the table named `dim_standard` (line 1097) is actually the strand-augmented standards table; the table named `dim_strand` (line 1128) is `(Identifier, Strand, ID, strand_ID)`. **Recommend renaming both for the dbt rebuild** to avoid confusion (e.g., `dim_standard_full`, `dim_strand_lookup`).

---

*End of spec. Total active code: ~2400 lines of notebook source. Word count ~3800.*
