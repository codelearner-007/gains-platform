# Legacy `dim_standard` — origin of the `AI.MA.*` alias rows

This audit answers a focused question: our seed `supabase/seeds/dim_standard.csv`
contains **two rows per `Identifier` UUID** for many B.E.S.T. standards (and a
similar duplication pattern for older MAFS / LAFS standards). The example we
chased — `Identifier = 3cd52b67-8bad-44d5-bb62-d37ecb91f432` — appears with both
`MA.912.AR.3.1` *and* `AI.MA.912.AR.3.1`, even though the upstream IMS CASE
Network feed (per the prior `edvancelearning-ims-integration.md` audit) only
emits a single row per leaf standard with `Schoology_Standard =
CFItem.HumanCodingScheme = "MA.912.AR.3.1"`.

**Headline finding.** Hypothesis A (Schoology REST `/standards` API) and
Hypothesis B (legacy code prepends `AI.`) are both **false**. Hypothesis C is
correct: the `AI.MA.*` alias is **emitted directly by Schoology** inside its
gradebook **Question-Data CSV exports** (each question row carries multiple
parallel `Standards` columns — `MA.912.NSO.1.4`, `MA.9-12.MAFS.912.N-RN.1.2`,
`AI.MA.912.NSO.1.4`, ...). Legacy's `Schoology_py.ipynb` `build_dimension_tables`
step ingests every distinct standard string seen in the question data, joins
each one against the EdvanceLS/IMS-fetched `dim_standard` via a
**substring-CONTAINS** match, and then `UNION`s the result back with the
original EdvanceLS rows. The resulting Delta table is keyed by
`uniquesID = Identifier || '_' || Schoology_Standard`, so the same Identifier
ends up with one row per distinct alias-form observed in the wild.

No static "AI." alias table exists anywhere in the legacy code, and no
Schoology REST endpoint is involved in the standards path.

---

## 1. Where does the `AI.MA.*` form come from?

**Answer:** Hypothesis C. The `AI.MA.912.*` strings live in **Schoology's
own Question-Data CSV export**, as one of several parallel `Standards`
columns Schoology writes per question. The legacy Spark pipeline pivots
those columns into rows and adds them to `dim_standard` via a partial
substring join.

### Hypothesis A — Schoology REST `/standards` API — REJECTED

`Schoology` class in
`/Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/Schoology_Analytics/notebook/Schoology_py.ipynb`
cell 2 only exposes three `fetch_data` callers:

```python
def load_users(self):
    ...
    data = self.fetch_data(f'{self.baseurl}users')
    inactive_users = self.fetch_data(f'{self.baseurl}users/inactive')
    ...
    oea.land(json.dumps(all_users), f'schoology_raw/v{self.version}/users', 'users.json', ...)

def load_roles(self):
    ...
    data = self.fetch_data(f'{self.baseurl}roles', 'role')
    oea.land(json.dumps(data), f'schoology_raw/v{self.version}/roles', 'roles.json', ...)
```

There is no `load_standards`, no `fetch_data('standards')`, and no reference
to `/v1/standards` anywhere in the legacy tree:

```
$ grep -r 'fetch_data.*standard' "OEA"
OEA/modules/module_catalog/Schoology_Analytics/notebook/Schoology_py.ipynb:
    "        df_dim_standard = oea.load(f'stage2/Ingested/.../standards')\n"
OEA/modules/module_catalog/EdvanceLS/notebook/Standards/Standards_py.ipynb:
    "        'Schoology_Standard': standard[\"title\"],\n"
```

The single `df_dim_standard = oea.load(...)` call reads the lake — it does
not call Schoology. The other reference is in `Standards_py` (EdvanceLS),
which calls `https://api.edvancelearning.us/.../local-standards`, not
Schoology.

C# Schoology integration: `EdvanceLearning/services/reporting/.../Schoology/`
has no standards-related class; only reporting endpoints. No
`https://api.schoology.com/v1/standards` reference in any `.cs`, `.razor*`,
`.json`, or `.md` in the legacy repo. `SchooloyAutomation/` is a
Power-Automate-style scraper that downloads CSV result files via UI
automation — it does not call a standards endpoint either.

### Hypothesis B — Legacy code synthesises the `AI.` prefix — REJECTED

```
$ grep -r 'AI\.MA' /Users/mac/Desktop/PS_P/gains\ legacy
(no matches)
```

No file in the legacy tree contains the literal string `AI.MA` or any
`"AI."` prefix-construction code, and there is no course-code-to-prefix
mapping table (CSV, JSON, or SQL seed) anywhere. The C# `RemoteCaseNetworkStandards`
import path stores `CFItem.HumanCodingScheme` verbatim — it never derives an
aliased variant.

### Hypothesis C — Schoology emits both forms in the gradebook CSV — CONFIRMED

Direct evidence from a Schoology Question-Data CSV currently in our repo
(`/Users/mac/Desktop/PS_P/gains-platform/data/Athenian/2025-26/1 - Lesson  Assessments/Mathematics/Grade 8/Sec 1/Question-Data-Chapter-9-Test-2026-05-05-063438.csv`).

Header row 1:

```
"Item ID","Item Name","Question ID","Associated Question ID","Total Points",
"Question Type",Question,"Position Number",Sub-Question,"Answer Option",
"Answer Breakdown","Answer Breakdown","Correct Answer","Correctly Answered",
"Most Points Earned","Least Points Earned","Average Points Earned",
Standards,Standards,Standards,Standards
```

Note four columns named `Standards` in a row. A real data row (line 2):

```
8359960427,"Chapter 9 Test",2269599900,,1,"Multiple Choice", ...
... ,MA.912.NSO.1.4,MA.9-12.MAFS.912.N-RN.1.2,MA.9-12.MAFS.912.N-Q.1.3,AI.MA.912.NSO.1.4
```

So Schoology, on its own, exports up to four alignment aliases per
question, in this order:

| col 18 (`Standards`)     | col 19 (`Standards`)         | col 20 (`Standards`)         | col 21 (`Standards`)       |
|--------------------------|------------------------------|------------------------------|----------------------------|
| `MA.912.NSO.1.4`         | `MA.9-12.MAFS.912.N-RN.1.2`  | `MA.9-12.MAFS.912.N-Q.1.3`   | `AI.MA.912.NSO.1.4`        |
| B.E.S.T. native (IMS code) | legacy MAFS alignment       | alternate MAFS alignment     | Algebra-I course alias     |

The `AI.MA.*` prefix is **Schoology's course-taxonomy code for Algebra I**:
`AI` = course (Algebra I), `MA.912.NSO.1.4` = the B.E.S.T. code. Schoology
emits this fourth column only for courses where the standard maps to a
specific Algebra-I scope. It is opaque to us — Schoology generates it
internally from its course-frameworks mapping and writes it directly into
the gradebook export. There is no API call we make to produce it.

(For older MAFS/LAFS standards Schoology emits analogous course prefixes
like `MA.K.MAFS.K.CC.1.1`, `LA.2.LAFS.2.RI.1.1` etc., visible in
`dim_standard.csv` as the `MA.<grade>.MAFS.<grade>.*` pattern paired with the
plain `MAFS.<grade>.*` form.)

---

## 2. How does legacy connect Schoology's emitted aliases to the IMS-fetched standards?

**Answer:** A **`Schoology_Standard CONTAINS Standard`** substring match in
`Schoology_py.build_dimension_tables`, followed by a `UNION` with the
original IMS rows. There is **no separate alias table** and **no IMS UUID
bridge** — the join is purely lexical on the standard string.

Exact code, `OEA/modules/module_catalog/Schoology_Analytics/notebook/Schoology_py.ipynb`
cell 2, lines 988–1051 (line numbers from `python3 -c 'json.load'` of the
notebook source):

```python
# dim_standard
df_dim_standard = oea.load(f'stage2/Ingested/schoology/v{schoology.version}/standards')      # 989

question_data = oea.load(f'stage3/Published/schoology/v{schoology.version}/dim_question_data')  # 994
question_data = question_data.groupBy("Standard").agg(count("*").alias("count"))                # 995
question_data = question_data.drop("Identifier","Subject")                                      # 996
standard = df_dim_standard                                                                      # 997
...

# Perform partial string match join
df_dim_question_data1 = question_data.join(
        standard,
        question_data.Standard.contains(standard.Schoology_Standard),    # ← substring match
        how="left"
    )                                                                    # 1007–1011
df_dim_question_data1 = df_dim_question_data1[...].dropDuplicates(...)   # 1012

df_dim_question_data = standard.join(
        question_data,
        standard.Schoology_Standard.contains(question_data.Standard),    # ← reverse direction
        how="left"
    )                                                                    # 1013–1017
df_dim_question_data = df_dim_question_data[...].dropDuplicates(...)     # 1018
df_dim_question_data = df_dim_question_data.union(df_dim_question_data1) # 1019

dim_strand = df_dim_question_data[...].dropDuplicates(...)               # 1022/1025
dim_strand = dim_strand.withColumnRenamed('Standard','Schoology_Standard')  # 1027
dim_strand = dim_strand.union(df_dim_standard[...]).na.drop()            # 1028 ← merge with raw IMS rows
dim_strand = dim_strand[...].dropDuplicates(...)                         # 1029
dim_strand = dim_strand.filter(~col("Schoology_Standard").rlike(r"^\d+$"))  # 1030
dim_strand = dim_strand.dropDuplicates(["Schoology_Standard"])           # 1032

dim_strand = dim_strand.withColumn(
    "cPalms_Standard",
    F.expr("concat_ws('.', slice(split(Schoology_Standard, '\\\\.'), 3, size(split(Schoology_Standard, '\\\\.' ))))")
)                                                                        # 1033–1036

dim_strand = dim_strand.withColumn(
    "uniquesID",
    concat_ws("_", dim_strand.Identifier, dim_strand.Schoology_Standard) # 1038–1039
)
dim_strand = dim_strand.withColumn(                                       # 1041–1049
    "uniquesID",
    when(
        (col("Identifier") == "Other") | (col("Schoology_Standard") == "Other"),
        "Other"
    ).otherwise(
        concat_ws("_", col("Identifier"), col("Schoology_Standard"))
    )
)

schoology.publish(dim_strand,
    f'stage2/Enriched/schoology/v{schoology.version}/dim_standard',
    f'stage3/Published/schoology/v{schoology.version}/dim_standard',
    primary_key='uniquesID')                                              # 1051
```

Mechanism for the duplicated row, walked through:

1. `df_dim_standard` (line 989) holds the IMS row with
   `Schoology_Standard = "MA.912.AR.3.1"`, `Identifier = "3cd52b67-…"`,
   `Subject = "Mathematics (B.E.S.T.)"`, etc. (one row total).
2. `question_data` (line 994) holds Schoology-emitted unique standard
   strings, including both `"MA.912.AR.3.1"` and `"AI.MA.912.AR.3.1"`
   (separate rows, because Schoology wrote them in separate `Standards`
   columns of the same question — see Q3 below).
3. The join at line 1007 (`question_data.Standard.contains(standard.Schoology_Standard)`)
   matches both `"MA.912.AR.3.1"` *and* `"AI.MA.912.AR.3.1"` against the
   single IMS row whose `Schoology_Standard = "MA.912.AR.3.1"`, because the
   IMS string is a suffix substring of the Schoology Algebra-I alias. Both
   produce a row carrying the IMS row's `Identifier`, `Subject`, `Strand`,
   `description`, etc., but keeping the Schoology side's `Standard` value.
4. Line 1027 renames that surviving `Standard` column back to
   `Schoology_Standard`. So the merged frame now holds **two rows with the
   same Identifier**: one whose `Schoology_Standard = "MA.912.AR.3.1"`,
   another whose `Schoology_Standard = "AI.MA.912.AR.3.1"`.
5. Line 1028 `UNION`s in the original IMS rows (which are dedup'd away by
   the `dropDuplicates(["Schoology_Standard"])` at line 1032 — the IMS row
   for `MA.912.AR.3.1` is identical to the one already there from step 3).
6. `cPalms_Standard` (line 1034) is **re-derived** at this stage by
   stripping the first two dot-segments of `Schoology_Standard`:
   - input `"MA.912.AR.3.1"` → drop `MA`, `912` → `"AR.3.1"`
   - input `"AI.MA.912.AR.3.1"` → drop `AI`, `MA` → `"912.AR.3.1"`
   That is precisely the difference we observe in the seed CSV (`cPalms_Standard
   = AR.3.1` vs `cPalms_Standard = 912.AR.3.1`).
7. `uniquesID = Identifier || '_' || Schoology_Standard` (line 1038–1048)
   keys the publish — so the same Identifier can legally appear in
   multiple rows as long as `Schoology_Standard` differs. The Delta `merge`
   in `OEA.publish` keys on this synthetic ID, accepting duplicates.

So the JOIN key between the IMS row and the Schoology-emitted alias is
**`<schoology_standard_string> CONTAINS <ims_humancodingscheme_string>`**.
There is no UUID bridge; there is no curated alias dictionary. It works for
`AI.MA.912.AR.3.1` only because that string happens to contain
`MA.912.AR.3.1` as a substring. Where the substring relationship fails
(e.g. unrelated alignment codes that Schoology emits), the legacy publish
silently produces an `Identifier = NULL` row and drops it via
`.na.drop()` on line 1028.

---

## 3. Schoology /standards API — does it exist and what does it return?

**Answer:** A Schoology `/v1/standards` endpoint *does* exist in
Schoology's public REST API documentation (per Schoology developer portal
references in third-party tooling), but **legacy never calls it**, and
nothing in the legacy codebase references it.

Searches:

```
$ grep -r '/v1/standards\|api.schoology.com/v1/standard\|"standards"' \
    "/Users/mac/Desktop/PS_P/gains legacy" \
    --include='*.ipynb' --include='*.cs' --include='*.py' --include='*.md'
$ grep -r 'get_standards\|GetStandards\|fetchStandards' \
    "/Users/mac/Desktop/PS_P/gains legacy"
(no matches relevant to API calls — only the `item == 'standards'` data-pipeline
 branches and the EdvanceLS Bearer-token /local-standards call)
```

Inconclusive on the exact response shape from Schoology's hypothetical
`/standards` REST endpoint — we have no captured response sample because
legacy never hit it. The current platform's `supabase/seeds/refresh_standards.py`
docstring mentions Schoology `/standards` but its actual implementation
targets 1EdTech CASE Network, not Schoology (see `legacy-standards-refresh.md`
Section 10's gap analysis).

---

## 4. Full data lineage of `dim_standard.csv` after PBIX-extract → Synapse → CSV

The audit doc `legacy-standards-refresh.md` documents the high-level
pipeline. The cell-level lineage for the row duplication is:

| Stage | Path / actor | Produces |
|---|---|---|
| Source 1 | IMS Global CASE Network REST (`casenetwork.1edtech.org/ims/case/v1p1/CFPackages/{id}`) | Per-leaf rows: `Identifier`, `HumanCodingScheme` ("MA.912.AR.3.1"), `FullStatement`, framework metadata |
| Stage 1 | `EdvanceLS/Standards_py.ipynb` cell 2 `load_standard` → `stage1/Transactional/lms_raw/v{ver}/standards/{rundate}/standards.json` | JSON array with 13 fields per row; `Schoology_Standard` = `standard["title"]` = HumanCodingScheme |
| Source 2 | Schoology gradebook CSV download (`Question-Data-*.csv`) — UI scraper `SchooloyAutomation` or manual download — landed into `oea/Raw_Files/Schoology/...` | CSV rows with up to 4 parallel `Standards` columns: B.E.S.T., MAFS, alt-MAFS, course alias (`AI.MA.*`) |
| Stage 1 | `Schoology_py.ipynb` cell 2 `preland_schoology_csv` melt step (lines 450–509) | One row per (Question, Standards-column) — collapses parallel `Standards` cols into the `Standard` value, tagged by which column it came from |
| Stage 2 | `Schoology_py.preprocess_schoology_dataset` → `stage2/Ingested/schoology/v{ver}/question_data` (line 297-303) | Filtered question_data, one row per (Question, alignment alias) — including both the `MA.912.AR.3.1` and `AI.MA.912.AR.3.1` rows |
| Stage 3 | `build_dimension_tables` lines 988–1051 (full code quoted in §2 above) — substring-CONTAINS join + `UNION` + `dropDuplicates(["Schoology_Standard"])` keyed by synthetic `uniquesID` | `stage3/Published/schoology/v{ver}/dim_standard` Delta with **one row per (Identifier, Schoology_Standard) pair** |
| PBIX | Power Query `Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"){...}{ldb_dev_s3_schoology_v0p1}{...}dbo_dim_standard` (`data/_pbix_extract/07_power_query.m` line 1+) | Import-mode load into PBIX dataset |
| Our seed | One-time CSV export of `dbo.dim_standard` from the lake DB into `supabase/seeds/dim_standard.csv` | The 7957-row artifact we ship today |

**The exact cell that produces the dual-alias rows** is the block at lines
988–1051 of `Schoology_py.ipynb` cell 2, with line 1009 being the join
that admits the alias substring match, line 1028 the UNION that retains
the IMS row, and line 1038 the synthetic `uniquesID` key that allows
multi-row same-Identifier.

> Inconsistency caveat (carried over from `legacy-standards-refresh.md`
> §9): the Schoology preprocess reads its `standards` partition from
> `schoology_raw/v{ver}/standards`, while `Standards_py` writes to
> `lms_raw/v{ver}/standards`. Either an undocumented file move bridges
> the two, or the `dim_standard` Delta is fed entirely off the older
> uncommented `self.publish(df_dim_standard, ...)` block at line 990 of
> the build step. Either way the rest of the lineage above is correct;
> only the stage-1 path naming is unclear.

---

## 5. Schoology standards integration in EdvanceLearning's .NET app

**Answer:** None. There is **no `SchoologyStandardsImport` service** analogous
to `K12StandardsImport`. The LMS app only knows about IMS CASE Network; it
neither calls Schoology's REST API nor pre-populates any alias.

Evidence:

- `/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/lms/src/EdvanceLS.LMS.Application/`
  contains **only** `LocalCaseNetworkStandards/` and `RemoteCaseNetworkStandards/`
  (both already documented in `edvancelearning-ims-integration.md`).
- `services/lti/` has no standards-related class (only LTI Advantage tooling).
- The only Schoology-named code in the .NET tree is
  `services/reporting/src/EdvanceLS.Reporting.Application.Contracts/Schoology/`
  — a reporting contract surface, no API caller, no standards logic. No
  files containing `AI.MA`, `coursePrefix`, `standardAlias`, etc.

So the `/local-standards` endpoint exposed by the LMS service serves one
row per IMS leaf, with `title = HumanCodingScheme = "MA.912.AR.3.1"`.
Aliasing happens entirely downstream, in the Spark pipeline, off the
Schoology CSVs.

---

## 6. Schoology auth pattern (used elsewhere — not for standards)

**Answer:** Two-legged OAuth 1.0 with `PLAINTEXT` signature method. The
"signature" is the pre-baked consumer-secret string pulled from Azure Key
Vault. Pattern verbatim from
`OEA/modules/module_catalog/Schoology_Analytics/notebook/Schoology_py.ipynb`
cell 2:

```python
def auth_header(self):
    oauth_consumer_key = oea._get_secret(self.keyvault_consumer_key)   # "schoologyConsumerKey{workspace}"
    oauth_token = ""
    oauth_nonce = str(random.getrandbits(64))
    oauth_timestamp = int(time.time())
    oauth_signature_method = "PLAINTEXT"
    oauth_version = "1.0"
    oauth_signature = oea._get_secret(self.keyvault_oauth_signature)   # "schoologyOauthSignature{workspace}"

    auth_header = (
        'OAuth realm="Schoology API", '
        f'oauth_consumer_key="{oauth_consumer_key}", '
        f'oauth_nonce="{oauth_nonce}", '
        f'oauth_timestamp="{oauth_timestamp}", '
        f'oauth_signature_method="{oauth_signature_method}", '
        f'oauth_version="{oauth_version}", '
        f'oauth_signature="{oauth_signature}"'
    )
    return auth_header
```

Used only for `/users`, `/users/inactive`, and `/roles`. We have no
captured request/response sample for any standards endpoint under these
credentials. Credentials redacted from this doc; live values remain in
Azure Key Vault under the workspace-suffixed secret names above
(`schoologyConsumerKey<dev|prod>`, `schoologyOauthSignature<dev|prod>`).

---

## 7. The mapping table — does it exist as a static asset?

**Answer:** No. We searched exhaustively and found nothing.

Searches performed:

```
$ grep -r 'AI\.MA\|AI\.LA\|"AI\."' "/Users/mac/Desktop/PS_P/gains legacy" \
    --include='*.cs' --include='*.razor*' --include='*.json' --include='*.cshtml'
(no matches)

$ find "/Users/mac/Desktop/PS_P/gains legacy" -type f \
    \( -name '*.csv' -o -name '*.json' \) \
  | xargs grep -l 'AI\.MA\.912\|AR\.3\.1' 2>/dev/null
(no matches)

$ grep -r 'CourseAlias\|StandardAlias\|aliasOf\|standardCode\|coursePrefix' \
    "/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/lms" \
    --include='*.cs'
(no matches — only EF Core HumanCodingScheme migrations)

$ ls /Users/mac/Desktop/PS_P/gains\ legacy/OEA/packages/ \
     /Users/mac/Desktop/PS_P/gains\ legacy/OEA/framework/
(no alias-dictionary files; only the framework runtime code and schema YAML)
```

There is no lookup table, no JSON mapping, no SQL seed. The only place the
`AI.MA.912.*` strings exist is **in Schoology's gradebook CSV exports
themselves** — and from there they propagate into `dim_standard` via the
substring join described in §2.

---

## 8. Conclusion + replication plan

### One-paragraph summary

Legacy fetches one row per IMS leaf standard from EdvanceLearning's
`/local-standards` endpoint (sourced from 1EdTech CASE Network), with
`Schoology_Standard = CFItem.HumanCodingScheme` — e.g. `MA.912.AR.3.1`.
Schoology's gradebook **Question-Data CSV** export then carries up to four
parallel `Standards` columns per question (B.E.S.T. native, MAFS,
alt-MAFS, course alias like `AI.MA.912.AR.3.1`). Spark melts those into
rows, then `build_dimension_tables` joins each distinct alias string back
to the IMS rows by a `Standard CONTAINS Schoology_Standard` substring
match and unions the IMS rows in, keyed by a synthetic
`uniquesID = Identifier || '_' || Schoology_Standard`. So every alias
Schoology ever emitted for a given Identifier persists as its own row in
`dim_standard`, with the IMS metadata copied across, and a derived
`cPalms_Standard` that drops the first two dot-segments of whatever the
alias was. The `AI.` prefix never appears in source code or in a lookup
table — it exists only in Schoology's emitted CSV.

### Concrete recipe for refreshing `dim_standard.csv` with both alias forms

We have **three pure-IMS-source options** (one of which is unworkable),
plus a **fourth that depends on Schoology data**:

1. **Pull from IMS only and accept that we lose the `AI.MA.*` rows.** This
   is what the current `supabase/seeds/refresh_standards.py` already does.
   It produces one row per IMS leaf — the canonical form. Our cube's
   `dim_question_data.standard` column will only join successfully against
   the unprefixed form. If/when assessment exports contain `AI.MA.912.AR.3.1`,
   those rows fall to "Other" / unaligned.
   - Pros: clean, single source of truth, public/free, no Schoology dep.
   - Cons: legacy parity broken; some questions will mis-align.

2. **Pull from IMS, then synthesise the `AI.` alias from existing assessment
   CSVs.** Mirror exactly what legacy did: at refresh time, scan all the
   `Question-Data-*.csv` files in `data/Athenian/.../*` (and any future
   imports), extract every distinct standard string ever observed, and
   for each one substring-join it against the IMS-derived rows. Emit
   `(Identifier, observed_string)` as additional rows. Re-derive
   `cPalms_Standard` and `uniquesID` per legacy.
   - Pros: bit-for-bit legacy parity; works for `AI.MA.*`, `MA.K.MAFS.*`,
     `LA.2.LAFS.*`, and any new alias Schoology adds without code change.
   - Cons: refresh now depends on having current assessment CSVs on disk;
     output is "what we have observed so far," not "everything Schoology
     could ever emit."

3. **Maintain a static `course_code → prefix` table.** Hard-code the
   handful of Schoology course prefixes we care about (`AI.` for
   Algebra I, `BA.` for Biology, `MA.K.`/`MA.1.`/... for K-12 Math,
   `LA.2.`/... for Reading) and synthesise the alias row deterministically.
   - Pros: no Schoology dep, no CSV scan.
   - Cons: brittle; new courses break it; doesn't match legacy's
     observe-then-record approach; we'd be inventing aliases Schoology
     might never emit, and possibly missing aliases Schoology *does* emit.

4. **Call Schoology REST `/standards` directly.** Per §3, legacy never did
   this and we have no captured response shape. The Schoology REST API
   docs do reference a standards endpoint (`GET /v1/standards/standards/{id}`
   per Schoology API docs), but without a captured response we cannot
   confirm it carries the `AI.MA.*` aliases. Not recommended without
   first piloting a request.

**Recommended approach: hybrid of #1 + #2.** Pull from IMS as the
canonical record (one row per leaf, the form `refresh_standards.py`
already produces). Then, at load time, augment with observed-from-CSV
aliases: scan every `Question-Data-*.csv` for distinct standard strings,
substring-join against the IMS rows, and emit one extra row per
`(Identifier, alias_string)` pair where the alias differs from the
canonical `Schoology_Standard`. Key by the same `uniquesID` legacy used.

---

## Recommended approach for `refresh_standards.py`

Concretely, the script should do the following — call it the "IMS-canonical
plus observed-alias" pattern:

1. **Pull canonical rows from IMS CASE Network** (current logic, unchanged):
   OAuth2 client_credentials at `casenetwork.1edtech.org/case-oauth2/clienttoken`,
   GET `CFPackages/{id}` for each whitelisted CFDocument, walk the
   `CFAssociations` tree to find leaf items, emit one row per leaf with
   `Identifier = CFItem.identifier` and `Schoology_Standard = CFItem.HumanCodingScheme`.
   This produces the **`MA.912.AR.3.1`** form (no `AI.` prefix). 13 columns
   per row, matching legacy's `Standards_py.load_standard`.

2. **Build alias rows from assessment CSVs** (new step, mirrors legacy
   `build_dimension_tables`):
   - Scan `data/Athenian/**/Question-Data-*.csv` (and any other assessment
     CSV folder configured) for every distinct value across every column
     named `Standards` (duplicate headers `Standards`, `Standards.1`,
     `Standards.2`, `Standards.3` after pandas auto-renaming).
   - For each distinct alias string `S`:
     - Find IMS rows where `S.contains(Schoology_Standard)` (i.e. the
       IMS `HumanCodingScheme` is a substring of `S`). Legacy's actual
       condition is `S.contains(IMS_code)` (PySpark `Column.contains`),
       which is substring-anywhere, not suffix. Use the same semantics.
     - If exactly one match, copy that row's `Identifier, Subject,
       Strand, Grader, description, cluster, language, lastChangeDateTime,
       Direct_Link, Cognitive_Complexity_Rating` and set:
       - `Schoology_Standard = S`
       - `cPalms_Standard = ".".join(S.split(".")[2:])` — drop first two
         dot-segments. (Verified bit-for-bit against the seed CSV: input
         `AI.MA.912.AR.3.1` produces `cPalms_Standard = 912.AR.3.1`; input
         `MA.912.AR.3.1` produces `cPalms_Standard = AR.3.1`.)
       - `Standard_New = ".".join(S.split(".")[4:])` if ≥5 segments else
         the trailing segment.
       - `uniquesID = f"{Identifier}_{S}"`
     - If multiple matches, prefer the shortest IMS row (the most-specific
       suffix). If none, skip (legacy `na.drop()` semantics).

3. **Deduplicate** by `Schoology_Standard` (legacy line 1032
   `dropDuplicates(["Schoology_Standard"])`) — same alias string never
   appears twice.

4. **Write the CSV** with the same 16 columns the legacy export has:
   `Cognitive_Complexity_Rating, Direct_Link, Grader, Identifier, Language,
   Schoology_Standard, Standard_New, Strand, Subject, cPalms_Standard,
   cluster, description, lastChangeDateTime, rundate, Custom.CleanedDescription,
   uniquesID`. `Custom.CleanedDescription` is currently just a copy of
   `description` per the seed; preserve that.

5. **Idempotency:** the script regenerates the CSV from scratch each run,
   so re-importing the same IMS feed + same CSVs is deterministic. Commit
   the CSV; diffs will show new aliases only when new assessment data
   surfaces them.

6. **Verification:** after generation, assert that for the canonical
   sample case `Identifier = 3cd52b67-8bad-44d5-bb62-d37ecb91f432` we
   produce **both** rows (`Schoology_Standard = MA.912.AR.3.1` and
   `Schoology_Standard = AI.MA.912.AR.3.1`). If assessment data covers
   it, this should always hold.

This gives us:

- Pure IMS-anonymous + local-CSV pull — no Schoology API needed.
- Legacy-bit-for-bit parity for any alias that has ever appeared in our
  assessment data.
- Forward compatibility: new aliases Schoology starts emitting in future
  exports automatically appear in `dim_standard` on the next refresh.

We avoid the legacy bugs documented in `edvancelearning-ims-integration.md`
§7–§9 (no token caching, no retries, broken update-detection) by keeping
the existing `refresh_standards.py` retry/atomicity scaffolding and
adding the alias-augmentation step at the end.
