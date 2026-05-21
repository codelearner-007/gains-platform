# Legacy `dim_standard` refresh — end-to-end audit

This document reconstructs how the legacy gains program populated and refreshed the
`dim_standard` table (the upstream of `supabase/seeds/dim_standard.csv` in our
current platform).

**Headline finding** — the source of truth is NOT Schoology's `/standards` API as
the current platform's `supabase/seeds/refresh_standards.py` docstring assumes.
Legacy fetches standards from **EdvanceLearning's own LMS service**
(`https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/local-standards`),
which in turn is populated from the **IMS Global CASE Network 1.0 REST API**
(`CFDocuments`, `CFItems`, `CFAssociations`, …) by a manual Blazor admin UI in
the LMS app. The Synapse pipeline that loads `dim_standard` is named
`3_Standards`, calls a notebook called `Standards_connector` →`Standards_py` in
the **EdvanceLS** OEA module (not the Schoology module), and is wired to a
monthly Synapse `ScheduleTrigger` that is currently `"runtimeState": "Stopped"`.

The notebook `Schoology_py.ipynb` does have logic that reads `standards` JSON
from `stage1/Transactional/schoology_raw/v{version}/standards/...` and joins it
into `dim_question_data`, but the only code path that *writes* those JSON files
is in the EdvanceLS Standards module (`Standards_py.ipynb` → `oea.land(... ,
'lms_raw/v{version}/standards', 'standards.json', ...)`). I could not find a
matching `schoology_raw/.../standards` writer in the Schoology notebook. The
spec file `data/_pbix_extract/40_schoology_py_spec.md:518` (which says
"Standards source: Schoology /standards API → JSON") therefore appears to be
**incorrect** — it conflated path naming with the source. See Section 1.

---

## 1. Source of truth

**Answer:** Legacy hits `GET https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/local-standards`,
a custom EdvanceLearning LMS endpoint backed by a Postgres LMS database that
was previously populated from IMS Global's CASE Network REST API
(`CFDocuments`, `CFItems`, `CFAssociations`, `CFPackages`, …). The Schoology
REST `/standards` endpoint is **not** called anywhere in the legacy codebase.

### Implementation (verbatim)

`/Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/EdvanceLS/notebook/Standards/Standards_py.ipynb` cell 2:

```python
class EdvanceLS:
    def __init__(self, workspace="dev", version="0.1"):
        self.baseurl = "https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/"
        self.tokenurl = "https://auth.edvancelearning.us/connect/token"
        self.version = version
        self.keyvault_consumer_key = f'caseNetworkConsumerKey{workspace}'
        self.keyvault_consumer_secret = f'caseNetworkConsumerSecret{workspace}'

    def get_access_token(self):
        token_url = self.tokenurl
        payload = {
            "client_id": oea._get_secret(self.keyvault_consumer_key),
            "client_secret": oea._get_secret(self.keyvault_consumer_secret),
            "grant_type": "client_credentials",
            "scope":"LMSService"
        }
        response = requests.post(token_url, data=payload)
        if response.status_code == 200:
          return response.json().get("access_token")
        else:
          print("Failed to obtain access token:", response.text)

    def fetch_standard(self):
        access_token = self.get_access_token()
        api_url = f"{self.baseurl}local-standards"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
          return response.json()
        else:
          print("Failed to make API request:", response.text)
          return None

    def load_standard(self):
        cfPackage = self.fetch_standard()
        standards = []
        if cfPackage:
            for cfdocument in cfPackage:
                for gradeLevel in cfdocument["items"]:
                    for strand in gradeLevel["children"]:
                        for cluster in strand["children"]:
                            for standard in cluster["children"]:
                                parseStandard = standard["title"].split(".")
                                cpalmsStandard = ".".join(parseStandard[2:])
                                shortStandard = ".".join(parseStandard[4:])
                                standardObj = { 'Identifier': standard["identifier"],
                                                'Language': standard["language"],
                                                'Schoology_Standard': standard["title"],
                                                'cPalms_Standard': cpalmsStandard,
                                                'description': standard["description"],
                                                'cluster': cluster["title"],
                                                'Subject':cfdocument["cFDocument"]["subject"][0],
                                                'Grader':gradeLevel["title"],
                                                'Strand':strand["title"],
                                                'Cognitive_Complexity_Rating':'',
                                                'lastChangeDateTime':standard["lastChangeDateTime"],
                                                'Direct_Link':cfdocument["cFDocument"]["uri"],
                                                'Standard_New':shortStandard
                                               }
                                standards.append(standardObj)
        currentDate = datetime.datetime.now()
        currentDateTime = currentDate.strftime("%Y-%m-%d")
        oea.land(json.dumps(standards), f'lms_raw/v{self.version}/standards', 'standards.json', oea.DELTA_BATCH_DATA, currentDateTime)
```

Notes:
- Request shape: plain `GET` with a `Bearer` token header, **no query params, no pagination**. The endpoint returns a single nested JSON tree (`CFPackage[] → items[] → children[] → children[] → children[]`) representing
  CFPackage → grade level → strand → cluster → standard.
- API base: `https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/`.
  Auth base: `https://auth.edvancelearning.us/connect/token` (IdentityServer-style
  OIDC client-credentials).
- The 13 columns it emits (`Identifier`, `Language`, `Schoology_Standard`,
  `cPalms_Standard`, `description`, `cluster`, `Subject`, `Grader`, `Strand`,
  `Cognitive_Complexity_Rating`, `lastChangeDateTime`, `Direct_Link`,
  `Standard_New`) line up 1:1 with the columns in
  `/Users/mac/Desktop/PS_P/gains-platform/supabase/seeds/dim_standard.csv`.
- The column name `Schoology_Standard` is misleading — the value is just the
  CASE Network standard `title`, which happens to match what Schoology stores.

### Where the EdvanceLearning LMS DB gets the data from

The LMS-side endpoint is implemented in
`/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/lms/src/EdvanceLS.LMS.Application/LocalCaseNetworkStandards/LocalCaseNetworkStandards.cs:142`:

```csharp
[Authorize(PermissionConstants.ImsCaseNetworkConstant.Read)]
public async Task<List<CFPackageTreeView>> GetLocalStandards()
{
    var cFPackageTreeViews = new List<CFPackageTreeView>();
    var cfItem = _cfPackage.WithDetailsAsync().Result
        .Include(x => x.CFAssociations).ThenInclude(x => x.originNodeURI)
        .Include(x => x.CFAssociations).ThenInclude(x => x.destinationNodeURI)
        .Include(x => x.CFItems).ThenInclude(x => x.CFItemTypeURI)
        .Include(x => x.CFDefinitions).ThenInclude(x => x.CFConcepts)
        ...
```

It reads the LMS service's own Postgres tables (`CFPackage`, `CFDocument`,
`CFItem`, `CFAssociation`, `CFDefinitions`, …). Those tables are populated by
the **K12StandardsImport** Blazor admin page
(`/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/lms/src/EdvanceLS.LMS.Blazor/Pages/K12StandardsImport.razor.cs:14`),
which calls `IRemoteCaseNetworkStandards`. That service hits the public IMS Global
CASE Network REST API:

`/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/lms/src/EdvanceLS.LMS.Application/RemoteCaseNetworkStandards/RemoteCaseNetworkStandards.cs:428`:

```csharp
var caseNetworkApiEndpoint = $"{_configuration["ImsCaseNetwork:apiEndpoint"]}CFDocuments";
var responseData = await ImsCaseNetworkApiCall(caseNetworkApiEndpoint);
```

with siblings `CFAssociations/{id}`, `CFAssociationGroupings/{id}`,
`CFConcepts/{id}`, `CFDocuments/{id}`, `CFItems/{id}`, `CFItemAssociations/{id}`,
`CFItemTypes/{id}`, `CFLicenses/{id}`, `CFRubrics/{id}`, `CFSubjects/{id}`,
`CFPackages/{id}` (lines 428–604). Auth in that call uses
`ImsCaseNetwork:clientId` + `clientSecret` from `IConfiguration`
(`RemoteCaseNetworkStandards.cs:619`).

So the full chain is:

```
IMS Global CASE Network REST API  (CFDocuments, CFItems, CFAssociations…)
        │  (admin manually triggers "Import" in Blazor UI: K12StandardsImport.razor)
        ▼
EdvanceLS LMS Postgres tables (CFPackage / CFDocument / CFItem / …)
        │  (Bearer-token GET /local-standards)
        ▼
Synapse Spark notebook Standards_py.load_standard()
        │  (oea.land(..., 'lms_raw/v{version}/standards', ...))
        ▼
ADLS Gen2: stage1/Transactional/lms_raw/v{version}/standards/delta_batch_data/rundate=YYYY-MM-DD/standards.json
        │  (Schoology_py.preprocess + ingest)
        ▼
stage2/Ingested/schoology/v{version}/standards   (Delta)
        │  (Schoology_py.build_dimension_tables → publish)
        ▼
stage3/Published/schoology/v{version}/dim_standard  (Delta + Synapse lake DB)
        │  (PowerBI Sql.Databases live)
        ▼
PBIX dataset on Synapse Serverless SQL (ldb_dev_s3_schoology_v0p1.dbo.dim_standard)
```

> **Spec correction.** `data/_pbix_extract/40_schoology_py_spec.md:518` ("Standards
> source: Schoology /standards API → JSON") is wrong. There is no
> `Schoology.fetch_data('standards')` call anywhere in
> `Schoology_py.ipynb`; the `Schoology` class only loads `users`, `roles`,
> CSVs from prelanding, and `users/inactive`. The notebook's
> `preprocess_schoology_dataset` *does* handle an `item == 'standards'`
> sub-folder in `stage1/Transactional/schoology_raw/...`, but that path is
> never written by Schoology_py itself — the spec evidently misread that block.
> The actual writer is the EdvanceLS Standards_py notebook landing into
> `lms_raw/v{version}/standards` (and the Schoology `preprocess` step must
> have historically been re-pointed at `lms_raw`, OR the data was hand-moved.
> See Section 9 for the small inconsistency).

---

## 2. Authentication / credentials

**Answer:** OAuth 2.0 **client credentials** flow against
EdvanceLearning's auth server, using `client_id` / `client_secret` pulled from
**Azure Key Vault** via the OEA framework helper `oea._get_secret`. The
Schoology consumer key/secret in the Schoology module is a separate concern
(used for `/users`, `/roles` only — **not** for standards).

### Standards (EdvanceLS) — verbatim
`Standards_py.ipynb` cell 2:

```python
self.keyvault_consumer_key = f'caseNetworkConsumerKey{workspace}'
self.keyvault_consumer_secret = f'caseNetworkConsumerSecret{workspace}'
...
payload = {
    "client_id": oea._get_secret(self.keyvault_consumer_key),
    "client_secret": oea._get_secret(self.keyvault_consumer_secret),
    "grant_type": "client_credentials",
    "scope":"LMSService"
}
response = requests.post(token_url, data=payload)
```

Secret names are workspace-suffixed: `caseNetworkConsumerKeydev`,
`caseNetworkConsumerKeyprod`, etc.

The Key Vault wrapper itself
(`/Users/mac/Desktop/PS_P/gains legacy/OEA/framework/synapse/notebook/OEA_py.ipynb` cell 0):

```python
def _get_secret(self, secret_name):
    """ Retrieves the specified secret from the keyvault. """
    sc = SparkSession.builder.getOrCreate()
    token_library = sc._jvm.com.microsoft.azure.synapse.tokenlibrary.TokenLibrary
    value = token_library.getSecret(self.keyvault, secret_name, self.keyvault_linked_service)
    return value
```

`self.keyvault_linked_service = 'LS_KeyVault'`; the Key Vault name is the global
`oea_keyvault` configured at notebook top (`oea_keyvault = 'yourkeyvault'`
is the placeholder in the source-controlled copy).

### Schoology (NOT used for standards, but FYI)
`Schoology_py.ipynb` cell 2:

```python
self.keyvault_consumer_key = f'schoologyConsumerKey{workspace}'
self.keyvault_oauth_signature = f'schoologyOauthSignature{workspace}'
...
oauth_signature_method = "PLAINTEXT"
oauth_version = "1.0"
oauth_signature = oea._get_secret(self.keyvault_oauth_signature)
auth_header = ('OAuth realm="Schoology API", '
               f'oauth_consumer_key="{oauth_consumer_key}", '
               f'oauth_nonce="{oauth_nonce}", '
               f'oauth_timestamp="{oauth_timestamp}", '
               f'oauth_signature_method="{oauth_signature_method}", '
               f'oauth_version="{oauth_version}", '
               f'oauth_signature="{oauth_signature}"')
```

i.e. Schoology uses **two-legged OAuth 1.0 with PLAINTEXT signature** (the
"signature" is literally just the pre-baked consumer-secret string stored in
Key Vault under `schoologyOauthSignaturedev`). This is what
`supabase/seeds/refresh_standards.py` in our platform models — but the
endpoint it would hit (`/standards`) is *not* the legacy source.

---

## 3. Storage tiers

**Answer:** Three-tier ADLS Gen2 lakehouse (OEA convention): stage1 raw JSON →
stage2 Delta → stage3 published Delta (also registered as a Synapse Lake DB).

### URL convention
`OEA_py.ipynb` cell 0:

```python
self.stage1 = f'abfss://oea@{self.storage_account}.dfs.core.windows.net/dev/stage1'
self.stage2 = f'abfss://oea@{self.storage_account}.dfs.core.windows.net/dev/stage2'
self.stage3 = f'abfss://oea@{self.storage_account}.dfs.core.windows.net/dev/stage3'
```

(In `prod`, the containers are top-level `abfss://stage1@...`, `stage2@...`,
`stage3@...`.) Storage account is set by `oea_storage_account` (placeholder
`'yourstorageaccount'` in the open-source copy).

### Stage 1 — raw landing (Transactional)
`OEA_py.ipynb` cell 0, `OEA.land`:

```python
def land(self, data, entity_path, filename=None, batch_data_type=DELTA_BATCH_DATA, rundate=None):
    ...
    sink_path = f'stage1/Transactional/{entity_path}/{batch_data_type}/rundate={rundate}'
    ...
    elif isinstance(data, str):
        self.write(data, f'{sink_path}/{filename}')
```

For standards, the call site (`Standards_py.ipynb` cell 2) passes
`entity_path = f'lms_raw/v{self.version}/standards'`, `filename = 'standards.json'`,
`batch_data_type = oea.DELTA_BATCH_DATA`, so the on-disk path is:

```
abfss://.../dev/stage1/Transactional/lms_raw/v0.1/standards/delta_batch_data/rundate=YYYY-MM-DD/standards.json
```

### Stage 2 — ingested (Delta)
`Schoology_py.preprocess_schoology_dataset` reads the latest `rundate=` folder
under `stage1/Transactional/schoology_raw/v{version}/<item>` and emits Delta to
`stage2/Ingested/schoology/v{version}/<item>`. The exact lookup for `standards`:

`Schoology_py.ipynb` cell 2:

```python
if item == 'users' or item == 'roles' or item == 'standards':
    df = spark.read.json(oea.to_url(f'{table_path}/{batch_type}/rundate={latest_dt}/*.json'))
...
elif item == 'standards':
    df = df.withColumn('description', regexp_replace(df['description'], r'\\r\\n', ' '))
```

(See Section 9 for the path-naming inconsistency between `lms_raw` writer and
`schoology_raw` reader.)

### Stage 3 — published (Delta + Synapse lake DB)
The `build_dimension_tables` block in `Schoology_py.ipynb` (cell 2) loads the
ingested standards and either republishes them or just uses them to join into
`dim_question_data`:

```python
# dim_standard
df_dim_standard = oea.load(f'stage2/Ingested/schoology/v{schoology.version}/standards')
# self.publish(df_dim_standard, f'stage2/Enriched/schoology/v{self.version}/dim_standard',
#              f'stage3/Published/schoology/v{self.version}/dim_standard', primary_key='Identifier')
# oea.add_to_lake_db(f'stage2/Enriched/schoology/v{self.version}/dim_standard')
# oea.add_to_lake_db(f'stage3/Published/schoology/v{self.version}/dim_standard')
```

The republish lines are **commented out**, but elsewhere in the same notebook
the code reads `stage3/Published/schoology/v{self.version}/dim_standard` (line
~55600), meaning either (a) the commented `self.publish` was run once and the
published Delta is just left in place forever, or (b) the Standards pipeline
publishes through a different code path I did not locate. The Power Query
contract (Section 7) confirms `dbo.dim_standard` *does* exist in the Synapse
serverless lake DB `ldb_dev_s3_schoology_v0p1`, so something is publishing it.
The Synapse lake DB is registered with `oea.add_to_lake_db(...)`, which makes
the Delta folder visible as an external table in the serverless SQL pool.

---

## 4. Pipeline orchestration

**Answer:** **Azure Synapse Pipelines** (the Synapse rebrand of Azure Data
Factory). One pipeline per ingestion entity wraps a Synapse Notebook activity,
which dispatches into one method on the connector class.

### The Standards pipeline
`/Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/Schoology_Analytics/pipeline/3_Standards.json`:

```json
{
    "name": "3_Standards",
    "properties": {
        "activities": [{
            "name": "load_Standards",
            "type": "SynapseNotebook",
            "typeProperties": {
                "notebook": { "referenceName": "Standards_connector", "type": "NotebookReference" },
                "parameters": {
                    "method_name": { "value": "load_standard", "type": "string" }
                },
                "snapshot": true,
                "sparkPool": { "referenceName": "spark3p3sm", "type": "BigDataPoolReference" },
                "executorSize": "Small",
                "driverSize": "Small"
            },
            "policy": { "timeout": "0.12:00:00", "retry": 0, "retryIntervalInSeconds": 30 }
        }],
        "folder": { "name": "Schoology" },
        "lastPublishTime": "2024-02-12T09:40:20Z"
    },
    "type": "Microsoft.Synapse/workspaces/pipelines"
}
```

The `Standards_connector` notebook is a 4-cell dispatcher in
`/Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/EdvanceLS/notebook/Standards/Standards_connector.ipynb`:

- cell 1 declares pipeline-injected parameters: `workspace`, `version`,
  `method_name`, `kwargs` (a JSON-encoded string of kwargs).
- cell 2 `%run /Standards_py` loads the `EdvanceLS` class.
- cell 3 calls `edvanceLs.set_workspace(workspace)` and `set_version(version)`.
- cell 4 dispatches: `m = getattr(edvanceLs, method_name); result = m(**parsed_kwargs); mssparkutils.notebook.exit(result)`.
  (Legacy uses Python's built-in `eval` to parse the kwargs string — noted as
  a security smell but inherited from OEA's connector pattern.)

So the pipeline parameter `method_name = "load_standard"` is the dispatch key
into the `EdvanceLS` class defined in Section 1.

### The downstream pipeline (sibling, but does not refetch standards)
`0_main_schoology.json` is the main batch pipeline triggered when a Schoology
CSV `Success.txt` arrives in `pre_landing/` (BlobEventsTrigger
`0_batch_prelanding_storage_trigger`). It chains
`preprocess → ingestion → dimension tables → facts tables → cube tables → powerBI_datasets_update`,
all invoking `Schoology_connector` notebook (not `Standards_connector`). So the
end-to-end `dim_standard` refresh runs only when `3_Standards` is triggered —
not as part of the main batch.

I could find no `powerBI_datasets_update` pipeline JSON in the legacy tree
(`grep -l 'powerBI_datasets_update' modules/.../*.json` returned nothing). It
is referenced but not source-controlled — either lives in a different Synapse
artefact branch, or was authored only in the Synapse Studio workspace.
**Inconclusive — could not find the pipeline definition.**

---

## 5. Refresh cadence

**Answer:** **Monthly**, India Standard Time — but the trigger is currently
**stopped** in the source-controlled config.

`/Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/Schoology_Analytics/triggers/2_schedule_trigger_users_roles_standards.json`:

```json
{
    "name": "2_schedule_trigger_users_roles_standards",
    "properties": {
        "annotations": [],
        "runtimeState": "Stopped",
        "pipelines": [
            { "pipelineReference": { "referenceName": "1_load_users_schoology", "type": "PipelineReference" } },
            { "pipelineReference": { "referenceName": "2_load_roles_schoology", "type": "PipelineReference" } },
            { "pipelineReference": { "referenceName": "3_Standards",            "type": "PipelineReference" } }
        ],
        "type": "ScheduleTrigger",
        "typeProperties": {
            "recurrence": {
                "frequency": "Month",
                "interval": 1,
                "startTime": "2025-01-01T12:40:00",
                "timeZone": "India Standard Time"
            }
        }
    }
}
```

Key points:

- Same schedule trigger fires `users`, `roles`, **and** `standards` together —
  i.e. legacy treats these three as a single "reference/lookup" tier (see
  Section 9).
- Frequency: `Month / 1`, start `2025-01-01T12:40:00 IST`. So in
  steady-state it runs around the 1st of each month at 07:10 UTC.
- `runtimeState: "Stopped"` — the trigger is **disabled** in this Git copy.
  Either it is enabled-by-hand in the live Synapse workspace and the disabled
  state here is stale, or the team has been running standards refreshes
  manually (consistent with the Blazor `K12StandardsImport` admin UI). No
  per-environment differences (only one trigger file).
- No retry: pipeline activity has `"retry": 0`; the schedule trigger itself
  has no retry concept. A failed monthly run silently produces no new
  `rundate=` folder in stage1.

---

## 6. Per-record refresh strategy

**Answer:** **Full reload every run**, no cursor / no incremental logic. The
record carries a `lastChangeDateTime` field but it is only stored, not used to
filter.

Evidence:

- `Standards_py.load_standard` (Section 1) calls `GET .../local-standards` with
  **no query parameters** and serialises the entire returned tree to a JSON
  array. It then `oea.land(json.dumps(standards), …)`, which writes the whole
  JSON file as a new `rundate=` partition. There is no `since=` / `where=` /
  `lastChangeDateTime` filter applied to the HTTP request.
- The downstream stage2 ingestion (`Schoology_py.preprocess_schoology_dataset`)
  always reads `rundate={latest_dt}` (the most recent partition) and writes
  to stage2 Delta — i.e. each monthly run replaces stage2 wholesale via the
  later `publish` step (which uses Delta merge upserts keyed by `Identifier`).

`OEA_py.ipynb` cell 0, `OEA.upsert`:

```python
def upsert(self, df, destination_path, primary_key='id'):
    """ Upserts the data in the given dataframe into the specified destination
        using the given primary_key_column to identify the updates. If there
        is no delta table found in the destination_path, one will be created. """
    destination_url = self.to_url(destination_path)
    df = self.fix_column_names(df)
    df = df.dropDuplicates([primary_key])
    if DeltaTable.isDeltaTable(spark, destination_url):
        delta_table_sink = DeltaTable.forPath(spark, destination_url)
        delta_table_sink.alias('sink').merge(df.alias('updates'),
            f'sink.{primary_key} = updates.{primary_key}').when...
```

So the *physical* refresh strategy is "fetch everything every time, upsert by
`Identifier`". Records removed from the upstream CASE Network would NOT be
removed from stage3 (no delete-by-anti-join). The `lastChangeDateTime` column
is preserved in the dimension purely as an attribute, not as a watermark.

---

## 7. PBIX dataset refresh

**Answer:** Import mode against Synapse **serverless SQL** (`Sql.Databases`),
i.e. Power BI Service scheduled refresh re-imports the cube/dim tables from the
serverless SQL view of the Delta lake DB. I could find **no scheduled-refresh
metadata** in the extracted PBIX artefacts — that lives in the Power BI Service
workspace settings, not in the PBIX file.

Evidence from `/Users/mac/Desktop/PS_P/gains-platform/data/_pbix_extract/07_power_query.m`:

```m
// query: dim_standard
let
    Source = Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"),
    ldb_dev_s3_schoology_v0p1 = Source{[Name="ldb_dev_s3_schoology_v0p1"]}[Data],
    dbo_dim_standard = ldb_dev_s3_schoology_v0p1{[Schema="dbo",Item="dim_standard"]}[Data],
    #"Filtered Rows" = Table.SelectRows(dbo_dim_standard, each ([Identifier] <> null)),
    #"Added Custom" = Table.AddColumn(#"Filtered Rows", "Custom", each Html.Table([description],{{"CleanedDescription",":root"}})),
    #"Expanded Custom" = Table.ExpandTableColumn(#"Added Custom", "Custom", {"CleanedDescription"}, {"Custom.CleanedDescription"})
in
    #"Expanded Custom"
```

- Server: `syn-oea-prodtest2-ondemand.sql.azuresynapse.net` (Synapse Serverless
  SQL, "ondemand" suffix is the Synapse on-demand SQL pool DNS).
- Database: `ldb_dev_s3_schoology_v0p1` (the lake DB registered by
  `oea.add_to_lake_db('stage3/Published/schoology/v0.1/dim_standard')`).
- All `dim_*` and `cube_*` queries use the same `Sql.Database(s)` pattern with
  no `Query=` / direct-query indicator → **import storage mode** (Power BI
  Desktop default). DirectQuery would be modelled differently in the .pbix
  manifest (no `Table.SelectRows`/`Table.AddColumn` materialisations).
- Per `0_main_schoology.json` the pipeline calls `ExecutePipeline →
  powerBI_datasets_update` after the cube build (lines 320-345), with
  `waitOnCompletion: true` and `fileName` parameter forwarded. So after each
  data refresh the main Schoology pipeline **explicitly kicks the Power BI
  dataset refresh** (presumably via the Power BI REST API's
  `/datasets/{id}/refreshes` endpoint, called by an Azure Function or Logic App
  invoked from `powerBI_datasets_update` — whose JSON was not in the source
  tree, see Section 4). For the Standards pipeline `3_Standards`, there is **no
  equivalent powerBI_datasets_update step**, so a standards-only refresh does
  NOT trigger the dashboard refresh.

---

## 8. Failure / observability

**Answer:** Bare-minimum — Python `print(...)` to notebook stdout on HTTP
failure, no metrics export, no alerting wired up in source. Synapse pipeline
activity logs are the only durable signal.

Evidence:

- `Standards_py.fetch_standard` / `get_access_token`:
  ```python
  else:
    print("Failed to obtain access token:", response.text)
  ...
  else:
    print("Failed to make API request:", response.text)
    return None
  ```
  - on failure it returns `None`, and `load_standard`'s `if cfPackage:` guard
  then writes an **empty `[]` JSON to ADLS** instead of erring out. So a 500 from
  the LMS would still produce a (successful-looking) pipeline run with an empty
  Delta partition — silently zeroing-out stage2/stage3 standards. (Combined with
  the upsert-by-Identifier publish in Section 6, the existing stage3 rows
  would survive, but a "monthly refresh ran and produced 0 rows" would be
  invisible.)
- Pipeline activity `policy.retry = 0` — no automatic retry on transient
  failures.
- No `logger.error` / `logger.exception` calls in `Standards_py`.
- No App Insights, no Slack/email webhook, no `oea.alert(...)` helper found in
  `OEA_py.ipynb`. `logger = logging.getLogger('OEA')` exists but only `info`
  and `warning` calls.
- The notebook would surface a non-`exit(...)` exception to Synapse, which would
  mark the pipeline activity as **Failed** in Synapse's monitor — that is the
  effective observability surface.

**Inconclusive — could not find evidence** of email-on-failure or alerts. None
was wired up in the Git-tracked Synapse artefacts; if anything exists it would
be a Synapse Alert Rule configured at the workspace level (not in repo).

---

## 9. Other reference tables (sanity check)

**Answer:** Standards is treated as **one of three reference/lookup feeds**
batched together on the same monthly schedule with users and roles. It is NOT
special.

Evidence:

- `2_schedule_trigger_users_roles_standards.json` (Section 5) explicitly lists
  three pipelines: `1_load_users_schoology`, `2_load_roles_schoology`,
  `3_Standards`. The trigger name itself says "users_roles_standards" —
  legacy authors clearly grouped them.
- Each of those three has the same structural shape: a single Synapse Notebook
  activity calling `<x>_connector` with `method_name = "load_<x>"`. E.g.
  `1_load_users_schoology.json` (`load_users`) and the never-trigger
  `3_Standards.json` (`load_standard`) are templates of one another.
- The HOT data (assessment CSVs) is loaded by a *different* path entirely: the
  Blob-Created event trigger `0_batch_prelanding_storage_trigger`
  (`runtimeState: "Started"`, watching `/oea/blobs/pre_landing/.../Success.txt`)
  fires `0_main_schoology` which then runs preprocess→ingest→dim→fact→cube.
  i.e. legacy splits its data into two cadences: **event-driven for CSV drops**
  vs **monthly schedule for API-fetched lookups**.

### Inconsistency worth flagging

`Standards_py.load_standard` writes to **`stage1/Transactional/lms_raw/v0.1/standards/...`**
(its `entity_path` is `f'lms_raw/v{self.version}/standards'`), but
`Schoology_py.preprocess_schoology_dataset` reads its `standards` partition
from **`stage1/Transactional/schoology_raw/v0.1/standards/...`** (because
its caller passes `tables_source = stage1/Transactional/schoology_raw/v{version}`).

The two paths don't match. Possible explanations (none confirmed from the
codebase):
1. There is an undocumented intermediate step (Synapse activity or hand-run
   notebook) that copies `lms_raw/.../standards` → `schoology_raw/.../standards`.
2. The Standards pipeline produces the stage3 Delta directly via its own
   ingest path (not through Schoology_py's `preprocess` loop). The commented
   `self.publish(df_dim_standard, …)` block in `build_dimension_tables`
   suggests this was indeed once the case but is now commented out.
3. Stage3 `dim_standard` is effectively **frozen** since the commented-out
   publish never runs, and the live data the PBIX reads is whatever was last
   written when those lines were uncommented.

This matches the on-disk reality: our current platform's
`supabase/seeds/dim_standard.csv` is a one-time export that exhibits some
cross-row corruption (per `refresh_standards.py` docstring: *"the seed at
`supabase/seeds/dim_standard.csv` was originally exported from Schoology and
has cross-subject corruption"*) — exactly what you would expect from a stale,
manually-maintained Delta table.

---

## 10. What changed between legacy and our current platform, and what we'd need to match

### Gap analysis

| Concern | Legacy | Current `gains-platform` |
|---|---|---|
| Source endpoint | `https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/local-standards` (OAuth2 client-credentials) | `supabase/seeds/refresh_standards.py` targets Schoology `/standards` (wrong endpoint, OAuth1 PLAINTEXT) |
| Trigger | Synapse `ScheduleTrigger` monthly, IST, currently `Stopped` | None — `load_standards.py` is run by hand |
| Storage | ADLS Gen2 stage1 JSON → stage2 Delta → stage3 Delta (Synapse lake DB) | Single Postgres table `dim_standard` from CSV seed |
| Refresh strategy | Full pull → upsert by `Identifier` (no deletes) | Truncate-and-reload from CSV |
| Observability | Synapse pipeline activity status; `print` on HTTP fail; silent empty writes | `load_standards.py` exits with code on failure; idempotency check by row count |
| PBIX refresh | `Sql.Database(...)` import-mode -> kicked by `powerBI_datasets_update` Synapse activity (def not in repo) | N/A (we render reports server-side from Postgres cubes) |

### Recommendation (brief)

If we want to match legacy refresh capability, the minimum change set is:

1. **Fix the source.** Point `refresh_standards.py` at the legacy CASE Network
   path (or directly at the IMS Global CASE Network public API) instead of
   Schoology `/standards`. Auth becomes OAuth2 client-credentials, not OAuth1.
2. **Add scheduling.** A monthly cron (Postgres `pg_cron`, GitHub Action, or
   FastAPI background job) that calls `refresh_standards.py` followed by
   `load_standards.py --force` and then triggers our cube rebuild
   (`app.transformations.runner`). The legacy frequency was monthly; given the
   `lastChangeDateTime` data shows multi-month staleness, monthly is sufficient.
3. **Upsert, don't truncate.** Switch `load_standards.py` to a merge keyed on
   `Identifier` so partial-failure runs don't blow away the table. Match
   legacy's "no deletes" semantics until we have a reason to do otherwise.
4. **Observability.** Log row counts pre/post, fail loud on `cfPackage is None`
   (legacy's biggest weakness), emit a structured log to whatever monitoring
   surface we settle on. Don't repeat legacy's "0-row success" bug.
5. **Decide on the upstream contract.** Legacy required a manual Blazor admin
   to import from IMS Global CASE Network into the LMS Postgres before any
   refresh would produce non-stale data. Our platform has no equivalent admin
   UI, so we either (a) call IMS Global CASE Network directly, or
   (b) accept that standards is effectively a once-a-year snapshot and drop
   the refresh job entirely.

The 13 columns in our `dim_standard.csv` already match exactly what
`Standards_py.load_standard` emits, so the downstream schema requires no
change.
