# EdvanceLearning ↔ IMS Global CASE Network 1.0 — Integration Audit

End-to-end reverse-engineering of how the legacy EdvanceLearning LMS pulls
education-standards data from the IMS Global CASE Network REST API, persists
it locally, and re-exposes it to the Synapse `Standards_py` notebook as
`GET /LMS/api/app/local-case-network-standards/local-standards`. This is the
upstream of `supabase/seeds/dim_standard.csv` in this project.

This doc is meant to be enough for a third party to build a 1:1 mirror
without running EdvanceLearning.

> All quoted snippets are verbatim from
> `/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/...`.

---

## 1. The Blazor admin UI

**Page:** `/Importk12standard`, file
`services/lms/src/EdvanceLS.LMS.Blazor/Pages/K12StandardsImport.razor` +
`.razor.cs`. It is an ABP **Blazor WebAssembly** page that renders a Blazorise
`DataGrid` of CASE Network `CFDocuments` fetched live from IMS, lets the admin
tick checkboxes per document, and triggers the import via a single "Import"
toolbar button.

`K12StandardsImport.razor:25`:
```razor
@inherits AbpCrudPageBase<IRemoteCaseNetworkStandards, CFDocumentDto,Guid,GetCfDocumentInput,CFDocumentDto>
```

The data grid lists Title / Creator / Subject / Last Change DateTime
columns (`K12StandardsImport.razor:33-44`). Selection state is held in
`identifier : List<string>` (`K12StandardsImport.razor.cs:70`) which collects
the `Identifier` of every ticked `CFDocumentDto`
(`K12StandardsImport.razor.cs:72-90`).

Click handler — `K12StandardsImport.razor.cs:92-105`:
```csharp
protected async Task HandleSelection()
{
    // Call the API to import selected documents
    try
    {
        await remoteCaseNetworkStandards.Import(identifier);
        NavigationManager.NavigateTo("/k12standard");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error calling API: {ex.Message}");
    }
}
```

**State exposed to the admin:** none beyond the data grid and a navigate-on-success
redirect. **No progress bar, no error log, no history table.** Failures are
swallowed into `Console.WriteLine` (visible only in the WASM browser console).
After success the user is dropped on `/k12standard`
(`K12Standards.razor`) which lists the now-locally-persisted `CFDocument`s
read from the LMS DB.

The toolbar registration (`K12StandardsImport.razor.cs:63-69`) shows the
button is gated by the `CreatePolicyName` permission policy of the page —
which resolves to `PermissionConstants.OrganizationConstant.Create` per the
`[Authorize]` attribute on `Import` (Section 2).

---

## 2. The C# service backing the import

**Service:**
`services/lms/src/EdvanceLS.LMS.Application/RemoteCaseNetworkStandards/RemoteCaseNetworkStandards.cs:26`
— class `RemoteCaseNetworkStandards : LMSAppService, IRemoteCaseNetworkStandards`.

The entry point invoked by the Blazor button is
`RemoteCaseNetworkStandards.cs:70-104`:
```csharp
[Authorize(PermissionConstants.OrganizationConstant.Create)]
public async Task Import(List<string> identifier)
{
    try
    {
        var CfAllDocument = await GetAllCFDocuments();
        var ii = 1;
        foreach (var CFPackage in CfAllDocument)
        {
            if (identifier.Contains("all"))
            {
                importCfDocument(CFPackage);
            }
            else
            {
                foreach (var id in identifier)
                {
                    if (id == CFPackage.CFPackageURI.identifier)
                    {
                        await importCfDocument(CFPackage);
                        break;
                    }
                }
            }
        }
    }
    catch (Exception err)
    {
        Console.WriteLine(err.Message);
    }
}
```

Key observations:

- Iterates *all* CFDocuments returned by the IMS catalog and filters in C# by
  matching against the user's selected `CFPackageURI.identifier` list (a
  sentinel string `"all"` is supported to mean "import everything").
- For each match it calls `importCfDocument(CFPackage)` which in turn hits
  `GetCFPackage(Guid)` to pull the full bundle for that document.

**HTTP client:** raw `System.Net.Http.HttpClient` (instantiated per call —
`new HttpClient()` inside `using` — not pooled via `IHttpClientFactory`).
JSON deserialization uses **Newtonsoft.Json** (`Newtonsoft.Json.JsonConvert`).
The entire call path is in `ImsCaseNetworkApiCall(string)` at
`RemoteCaseNetworkStandards.cs:615-681` (quoted in full under Section 7).

**Auth scheme:** OAuth2 Client Credentials Grant. Service sends HTTP Basic
auth (`{clientId}:{clientSecret}` base64-encoded) to a token endpoint, then
uses the returned bearer token to GET the CASE resource. See Section 7.

**Request shape (per CASE resource):**
- Method: `GET`
- URL: `{ImsCaseNetwork:apiEndpoint}{Resource}/{guid}` or `{...apiEndpoint}CFDocuments`
- Headers:
  - `Authorization: bearer <access_token>` (lowercase `bearer` — `RemoteCaseNetworkStandards.cs:649`)
- No query params, no body.

---

## 3. IMS endpoint URLs

`services/lms/host/EdvanceLS.LMS.HttpApi.Host/appsettings.json:9-14`:
```json
"ImsCaseNetwork": {
  "clientId":     "<REDACTED — see legacy appsettings.json>",
  "clientSecret": "<REDACTED — see legacy appsettings.json>",
  "apiEndpoint":  "https://casenetwork.1edtech.org/ims/case/v1p1/",
  "accessToken":  "https://casenetwork.1edtech.org/case-oauth2/clienttoken"
},
```

`appsettings.Production.json:12` is identical (same host, same credentials).
Credentials redacted from this doc on 2026-05-21 — empirically verified
dead (HTTP 403 "Invalid credentials supplied") and should not be circulated
either way. The live values remain at the cited path in the legacy repo if
needed for reference. For our own pulls, request a fresh 1EdTech client
or use the CPALMS anonymous path (see refresh_standards.py).

> **Correction vs the prior audit assumption.** The brief said to look for
> `opensalt.imsglobal.org` and `cpalms.org`. Neither appears in the
> EdvanceLearning codebase. The live source is **1EdTech's** CASE Network
> hub at `casenetwork.1edtech.org/ims/case/v1p1/` (note: v1p1, not v1p0).
> The cPALMS-style URLs that surface in `dim_standard.csv`'s `Direct_Link`
> column are merely the `uri` fields of CFDocuments published by the FLDOE
> on the 1EdTech hub — they are payload, not endpoint.

**Endpoints actually called** — all via `ImsCaseNetworkApiCall`,
`RemoteCaseNetworkStandards.cs:428-613`:

| Method | Endpoint | Line |
|---|---|---|
| `GetAllCFDocuments` | `{base}CFDocuments` | 428 |
| `GetCFAssociation(id)` | `{base}CFAssociations/{id}` | 443 |
| `GetCFAssociationGrouping(id)` | `{base}CFAssociationGroupings/{id}` | 459 |
| `GetCFConcept(id)` | `{base}CFConcepts/{id}` | 475 |
| `GetCFDocument(id)` | `{base}CFDocuments/{id}` | 491 |
| `GetCFItem(id)` | `{base}CFItems/{id}` | 507 |
| `GetCFItemAssociation(id)` | `{base}CFItemAssociations/{id}` | 523 |
| `GetCFItemType(id)` | `{base}CFItemTypes/{id}` | 539 |
| `GetCFLicense(id)` | `{base}CFLicenses/{id}` | 555 |
| `GetCFRubric(id)` | `{base}CFRubrics/{id}` | 571 |
| `GetCFSubject(id)` | `{base}CFSubjects/{id}` | 587 |
| `GetCFPackage(id)` | `{base}CFPackages/{id}` | 603 |
| `GetListAsync` (page render) | `{base}CFDocuments` | 693 |

**Empirically used at import time:** only `CFDocuments` (catalog listing)
and `CFPackages/{id}` (full bundle per document). The other endpoint methods
are defined but never called by `Import` or `importCfDocument` — the
`CFPackage` response already contains the embedded `CFDocument`,
`CFItems[]`, `CFAssociations[]`, `CFRubrics[]`, and a nested `CFDefinitions`
object (which itself carries `CFConcepts`, `CFSubjects`, `CFLicences`,
`CFItemTypes`, `CFAssociationGroupings`).

Config-driven, not hardcoded: every URL is built as
`$"{_configuration["ImsCaseNetwork:apiEndpoint"]}<Resource>"`.

---

## 4. Data flow: CASE → EdvanceLearning DB

**Mapper:** **manual `new CFDocument { … }` constructions** — there is *no*
`Mapper.Map<>` / AutoMapper used on the inbound path. AutoMapper is only used
to project domain entities into DTOs for the Blazor UI (e.g.
`_mapper.Map<List<CFDocumentDto>>(items)` at line 710).

The full inbound mapping is `RemoteCaseNetworkStandards.cs:105-422`. Highlights:

CFDocument fields (`RemoteCaseNetworkStandards.cs:116-139`):
```csharp
var cFDocument = new CFDocument
{
    identifier = item.CFDocument.identifier,
    uri = item.CFDocument.uri,
    creator = item.CFDocument.creator,
    title = item.CFDocument.title,
    lastChangeDateTime = item.CFDocument.lastChangeDateTime,
    publisher = item.CFDocument.publisher,
    language = item.CFDocument.language,
    adoptionStatus = item.CFDocument.adoptionStatus,
    officialSourceURL = item.CFDocument.officialSourceURL,
    subject = item.CFDocument.subject,
    CFPackageURI = null,
    licenseURI = null,
    caseVersion = item.CFDocument.caseVersion,
    notes = item.CFDocument.notes,
    description = item.CFDocument.description,
    statusStartDate = item.CFDocument.statusStartDate,
    version = item.CFDocument.version,
    statusEndDate = item.CFDocument.statusEndDate,
    nodeTypeId = item.CFDocument.nodeTypeId,
    subjectURI = null,
    Id = Guid.NewGuid()
};
```
Note: `subject` is `List<string>`, and `subjectURI` / `licenseURI` /
`CFPackageURI` / `extensions` are owned navigation properties built
separately (lines 141-184).

CFItem fields (`RemoteCaseNetworkStandards.cs:246-261`):
```csharp
var cfItems = new CFItem()
{
    FullStatement = cfItem.FullStatement,
    CFPackageId = cfPackageId.Id,
    ListEnumeration = cfItem.ListEnumeration,
    EducationLevel = cfItem.EducationLevel,
    Type = cfItem.Type,
    CFItemTypeURI = null,
    licenseURI = null,
    Language = cfItem.Language,
    Identifier = cfItem.Identifier,
    Uri = cfItem.Uri,
    LastChangeDateTime = cfItem.LastChangeDateTime,
    HumanCodingScheme = cfItem.HumanCodingScheme,
    Id = Guid.NewGuid()
};
```

**Entity classes:** `services/lms/src/EdvanceLS.LMS.Domain/LTIModels/` —
`CFDocument.cs`, `CFItem.cs`, `CFPackage.cs`, plus sibling classes in the
same folder (CFAssociation, CFConcept, CFDefinitions, CFItemType, CFLicence,
CFRubric, CFSubject, CFAssociationGrouping, CFPackageUri, LicenseUri,
OriginNodeURI, DestinationNodeURI, CFAssociationGroupingURI, SubjectUri,
Extensions).

**Schema:** the EF Core migration that creates everything is
`services/lms/src/EdvanceLS.LMS.EntityFrameworkCore/Migrations/20240119125827_CaseNetwork.cs`.
Tables created include `CFDocuments`, `CFItems`, `CFItemAssociations`,
`CFItemTypes`, `CFItemTypeURIs`, `CFLicences`, `CFRubrics`,
`CFRubricCriterions`, `CFRubricCriterionLevels`, `CFSubjects`, `CFConcepts`,
`CFAssociations`, `CFAssociationGroupings`, plus owned-entity tables
`CFDocumentURI` and `CFAssociationGroupingURI` (migration lines 190–262,
1473–1546, 3380–3411). The connection string is **SQL Server**, not Postgres
(`appsettings.json:17` → `"LMSService": "Server=localhost,1433;Database=LMS;..."`).
The prior audit doc's "LMS Postgres DB" claim is incorrect — it's SQL Server.

**Relationships preserved via FK columns:**
- `CFPackage` has `CFDocumentId` (FK) and `CFDefinitionsId` (FK).
- `CFItem`, `CFAssociation`, `CFRubric` all have `CFPackageId` (FK) tying
  them to their parent bundle.
- `CFConcept`, `CFSubject`, `CFLicence`, `CFItemType`,
  `CFAssociationGrouping` all have `CFDefinitionsId` (FK).
- The hierarchical relationship between items (e.g. grade → strand →
  cluster → standard) is **not** stored as a self-referential FK on
  `CFItems`. Instead it lives in the `CFAssociations` table, where each row
  links an `originNodeURI` (child) to a `destinationNodeURI` (parent) of
  whatever `associationType` the framework uses ("isChildOf", typically).
  The tree is reconstructed at read time by
  `LocalCaseNetworkStandards.k12PackageChild` / `k12PackageSubChild`
  (Section 6).

---

## 5. Pagination + iteration

**The IMS catalog endpoint is fetched in a single non-paginated GET.**
`RemoteCaseNetworkStandards.cs:424-437`:
```csharp
public async Task<List<CFDocument>> GetAllCFDocuments()
{
    try
    {
        var caseNetworkApiEndpoint = $"{_configuration["ImsCaseNetwork:apiEndpoint"]}CFDocuments";
        var responseData = await ImsCaseNetworkApiCall(caseNetworkApiEndpoint);
        var cfItem = Newtonsoft.Json.JsonConvert.DeserializeObject<CFDocumentsRoot>(responseData);
        return cfItem.CFDocuments;
    }
    ...
```

`GetCFPackage` (line 599) is also a single GET — each `CFPackage` response
inlines its `CFItems[]`, `CFAssociations[]`, `CFDefinitions`, `CFRubrics[]`
in one JSON blob. No `?limit=`/`?offset=` query is ever set; no `Link` header
is parsed. The CASE 1.0 spec does not mandate pagination on these endpoints
and 1EdTech's hub returns the full list.

**Iteration loop** (`RemoteCaseNetworkStandards.cs:75-96`):
```csharp
var CfAllDocument = await GetAllCFDocuments();
foreach (var CFPackage in CfAllDocument)
{
    if (identifier.Contains("all"))
    {
        importCfDocument(CFPackage);   // NB: not awaited — fire-and-forget
    }
    else
    {
        foreach (var id in identifier)
        {
            if (id == CFPackage.CFPackageURI.identifier)
            {
                await importCfDocument(CFPackage);
                break;
            }
        }
    }
}
```

Selection is per-document (admin checks individual CFDocuments in the data
grid). The "all" branch fires off imports without awaiting them, which would
cause race conditions on EF Core — likely a latent bug.

---

## 6. The /local-standards output endpoint

**Service:**
`services/lms/src/EdvanceLS.LMS.Application/LocalCaseNetworkStandards/LocalCaseNetworkStandards.cs:142-163`:
```csharp
[Authorize(PermissionConstants.ImsCaseNetworkConstant.Read)]
public async Task<List<CFPackageTreeView>> GetLocalStandards()
{
    try
    {
        var cFPackageTreeViews = new List<CFPackageTreeView>();

        var cfItem = _cfPackage.WithDetailsAsync().Result
            .Include(x => x.CFAssociations).ThenInclude(x => x.originNodeURI)
            .Include(x => x.CFAssociations).ThenInclude(x => x.destinationNodeURI)
            .Include(x => x.CFItems).ThenInclude(x => x.CFItemTypeURI)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFConcepts)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFSubjects)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFItemTypes)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFLicences)
            .Include(x => x.CFDocument);
        foreach (var item in cfItem)
        {
            var cFPackageTreeView = new CFPackageTreeView();
            cFPackageTreeView.cFDocument = item.CFDocument;
            cFPackageTreeView.items = await k12PackageChild(item);
            cFPackageTreeViews.Add(cFPackageTreeView);
        }
        return cFPackageTreeViews;
    }
    ...
}
```

**Route:** ABP auto-generates REST routes from interface method names. The
interface is
`services/lms/src/EdvanceLS.LMS.Application.Contracts/LocalCaseNetworkStandards/ILocalCaseNetworkStandards.cs:20`:
```csharp
Task<List<CFPackageTreeView>> GetLocalStandards();
```
ABP turns `LocalCaseNetworkStandards.GetLocalStandards()` into
`GET /api/app/local-case-network-standards/local-standards` (camel-case
kebab-cased, "Get" prefix dropped). This matches the URL the Spark notebook
hits (`Standards_py.ipynb` → `https://api.edvancelearning.us/LMS/api/app/local-case-network-standards/local-standards`).

**Response JSON shape:**
- Top level: `CFPackageTreeView[]` — one per imported CFDocument.
- Each element has `cFDocument` (the full domain entity — title, creator,
  subject[], lastChangeDateTime, uri, etc.) and `items` (`IEnumerable<Item>`).
- `Item` (`LMS.Domain/LTIModels/CFItem.cs:48-63`):
```csharp
public class Item
{
    public string title { get; set; }
    public string? edLevel { get; set; }
    public string? description { get; set; }
    public string? type { get; set; }
    public string? language { get; set; }
    public string? identifier { get; set; }
    public string? lastChangeDateTime { get; set; }
    public IEnumerable<Item> Children { get; set; }
}
```

The tree is built by walking `CFAssociations` (where the document is the
destinationNodeURI of a top-level association, then recursing into items
that are themselves destinationNodeURIs of further associations) in
`k12PackageChild` (line 198) and `k12PackageSubChild` (line 257) of
`LocalCaseNetworkStandards.cs`.

Crucially, **at every level the `Item` fields are populated from the
underlying `CFItem` columns differently**:

For non-leaf inner nodes — `LocalCaseNetworkStandards.cs:206-211`:
```csharp
itemP.title = item.originNodeURI.title;   // ← CFAssociation.originNodeURI.title
var description = CFPackageList.CFItems.FirstOrDefault(...).HumanCodingScheme;
var type = CFPackageList.CFItems.FirstOrDefault(...).Type.ToLower();
var language = CFPackageList.CFItems.FirstOrDefault(...).Language.ToLower();
var lastChangeDateTime = CFPackageList.CFItems.FirstOrDefault(...).LastChangeDateTime.ToString();
```

For leaf standard nodes — `LocalCaseNetworkStandards.cs:219-228`:
```csharp
itemsP.title = CFPackageList.CFItems.FirstOrDefault(...).HumanCodingScheme;
itemsP.description = CFPackageList.CFItems.FirstOrDefault(...).FullStatement;
itemsP.type = CFPackageList.CFItems.FirstOrDefault(...).Type.ToLower();
itemsP.language = CFPackageList.CFItems.FirstOrDefault(...).Language.ToLower();
itemsP.identifier = CFPackageList.CFItems.FirstOrDefault(...).Identifier.ToLower();
itemsP.lastChangeDateTime = CFPackageList.CFItems.FirstOrDefault(...).LastChangeDateTime.ToString();
if (CFPackageList.CFItems.FirstOrDefault(...).EducationLevel != null)
{
    itemsP.edLevel = CFPackageList.CFItems.FirstOrDefault(...).EducationLevel.LastOrDefault();
}
```

So at the leaf depth — the depth at which `Standards_py` builds a row —
`title = CFItem.HumanCodingScheme` (e.g. `"VA.K.H.2.1"`), `description = CFItem.FullStatement`,
`identifier = CFItem.Identifier` (the UUID). For all parent levels, `title`
falls back to the CFAssociation node URI's `title` (which for FLDOE-style
frameworks is the grade-level / strand / cluster human-readable label) and
the leaf's HumanCodingScheme is squirreled into the local `description`
variable but **not** assigned to the parent `itemP.description`. Parent
`description` is therefore always null in the API response.

**Column-correlation to `dim_standard.csv`:** the
`Standards_py.load_standard()` walker (already quoted in the prior audit doc
at `legacy-standards-refresh.md`) reads
`cfPackage → cfdocument → items[gradeLevel] → children[strand] → children[cluster] → children[standard]`
and produces these 13 columns:

| `dim_standard` col | API field path | Origin in CFItem |
|---|---|---|
| `Identifier` | `standard["identifier"]` | `CFItem.Identifier` (UUID, lowercased) |
| `Language` | `standard["language"]` | `CFItem.Language` |
| `Schoology_Standard` | `standard["title"]` | `CFItem.HumanCodingScheme` (NB!) |
| `cPalms_Standard` | `".".join(parseStandard[2:])` | derived: `HumanCodingScheme` minus first two dot-segments |
| `description` | `standard["description"]` | `CFItem.FullStatement` |
| `cluster` | `cluster["title"]` | `CFAssociation.originNodeURI.title` (the cluster node's display title) |
| `Subject` | `cfdocument["cFDocument"]["subject"][0]` | `CFDocument.subject[0]` (first entry of `List<string>`) |
| `Grader` | `gradeLevel["title"]` | `CFAssociation.originNodeURI.title` at grade-level depth |
| `Strand` | `strand["title"]` | `CFAssociation.originNodeURI.title` at strand depth |
| `Cognitive_Complexity_Rating` | hardcoded `''` | not in IMS payload at all |
| `lastChangeDateTime` | `standard["lastChangeDateTime"]` | `CFItem.LastChangeDateTime.ToString()` |
| `Direct_Link` | `cfdocument["cFDocument"]["uri"]` | `CFDocument.uri` |
| `Standard_New` | `".".join(parseStandard[4:])` | derived: `HumanCodingScheme` minus first four dot-segments |

> "First four dot-segments" example: `VA.K.H.2.1` → drop `VA`, `K`, `H`, `2`
> → `Standard_New = "1"`. The CSV row we sampled has
> `Standard_New = 1, cPalms_Standard = H.2.1` for the input `VA.K.H.2.1`,
> consistent with the slicing.

`Custom.CleanedDescription`, `uniquesID`, and `rundate` in the published CSV
are downstream additions in the Synapse Schoology preprocess /
`build_dimension_tables` step — **they are not part of the IMS payload nor
of the LMS API response**. `uniquesID = f"{Identifier}_{Schoology_Standard}"`
empirically.

---

## 7. Auth (OAuth2 client credentials)

The IMS-side call uses HTTP Basic to fetch a bearer token. Quoted in full
from `RemoteCaseNetworkStandards.cs:615-681`:

```csharp
private async Task<string> ImsCaseNetworkApiCall(string caseNetworkApiEndpoint)
{
    try
    {
        var clientId = _configuration["ImsCaseNetwork:clientId"];
        var clientSecret = _configuration["ImsCaseNetwork:clientSecret"];
        var tokenEndpoint = _configuration["ImsCaseNetwork:accessToken"];

        // Define the parameters for the token request
        var content = new FormUrlEncodedContent(new[]
        {
             new KeyValuePair<string, string>("grant_type", "client_credentials")
        });
        using (var httpClient = new HttpClient())
        {
            var credentials = $"{clientId}:{clientSecret}";
            var base64Credentials = Convert.ToBase64String(Encoding.UTF8.GetBytes(credentials));
            var authHeader = new AuthenticationHeaderValue("Basic", base64Credentials);

            try
            {
                httpClient.DefaultRequestHeaders.Authorization = authHeader;
                // Make the token request
                var response = await httpClient.PostAsync(tokenEndpoint, content);

                // Handle the response
                if (response.IsSuccessStatusCode)
                {
                    // Read and parse the token from the response
                    var token = await response.Content.ReadAsStringAsync();
                    var tokenResponse = Newtonsoft.Json.JsonConvert.DeserializeObject<TokenResponse>(token);

                    var accessToken = tokenResponse.access_token;

                    httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("bearer", accessToken);

                    var response1 = await httpClient.GetAsync(caseNetworkApiEndpoint);

                    if (response1.IsSuccessStatusCode)
                    {
                        var responseData = await response1.Content.ReadAsStringAsync();
                        return responseData;
                    }
                    else
                    {
                        throw new Exception($"Ims Case Network API request failed with status code {response.StatusCode}");
                    }
                }
                else
                {
                    throw new Exception($"Ims Case Network API request failed with status code {response.StatusCode}");
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"Ims Case Network API request failed with status code");
            }
        }
    }
    catch (Exception ex)
    {
        throw new Exception($"An exception occurred: {ex.Message}");
    }
}
```

**Token endpoint:** `https://casenetwork.1edtech.org/case-oauth2/clienttoken`
**Resource endpoint:** `https://casenetwork.1edtech.org/ims/case/v1p1/...`
**Grant:** `client_credentials` (form body `grant_type=client_credentials`,
HTTP Basic auth header carrying `<clientId>:<clientSecret>` — see the
legacy appsettings.json for the literal values.
**Bearer header:** `Authorization: bearer <token>` (lowercase scheme; some
servers are picky and require `Bearer`, but 1EdTech accepts both).

A new token is requested **on every call** (no caching of access_token between
CFPackage fetches, despite the spec giving them `expires_in` minutes of life).

> The OAuth2 flow described on the Spark notebook side
> (`https://auth.edvancelearning.us/connect/token` with scope `LMSService`)
> is a **separate** auth boundary — that's the notebook authenticating to
> *EdvanceLearning's* OIDC server to call `/local-standards`. It has
> nothing to do with the IMS call. The two are unconnected.

The 1EdTech credentials above are **committed in plaintext** in
`appsettings.json:11` and `appsettings.Production.json:11`. If we mirror this
integration, we should treat them as compromised and request fresh ones
from 1EdTech.

---

## 8. Error handling, retries, observability

**Retries:** none. Single HTTP attempt per resource, no exponential backoff,
no `Polly` policy attached. The class does not register `IHttpClientFactory`
or any handler chain.

**Error handling:** all four levels of try/catch in `ImsCaseNetworkApiCall`
ultimately re-throw with hand-rolled `Exception` strings that *drop* the
inner exception. The deepest catch (`RemoteCaseNetworkStandards.cs:669-672`)
even loses the status code:
```csharp
catch (Exception ex)
{
    throw new Exception($"Ims Case Network API request failed with status code");
}
```
Callers of the per-resource Get* methods generally swallow exceptions and
return `null` (e.g. lines 449-451, 466-468, 482-484…). The top-level `Import`
method (line 98-101) catches and logs to `Console.WriteLine` — meaning in
the WASM Blazor environment, the error surfaces only in the user's browser
DevTools, not server logs.

**Rate limiting:** not honoured. No `Retry-After` parsing, no throttling. If
1EdTech's hub 429s, the import will hard-throw and the user must retry
manually.

**Logging / audit:** ABP's standard `IAuditingManager` is wired at the
framework level via the `[Authorize(...)]` attributes (which create entries
in ABP's `AbpAuditLogs` table per request), but no domain-level logging
(`ILogger<RemoteCaseNetworkStandards>`) is injected or used in this class.

---

## 9. Validation / idempotency

**De-dupe key:** `CFDocument.identifier` (the IMS UUID).

**Upsert behaviour** — `RemoteCaseNetworkStandards.cs:113-421`:

```csharp
var cfDocumentCheck = _repository.GetListAsync().Result
    .FirstOrDefault(x => x.identifier == item.CFDocument.identifier);
if (cfDocumentCheck == null)
{
    // ... full insert path: CFDocument, then CFPackage row, then
    //     bulk InsertManyAsync of CFAssociations, CFItems, CFConcepts,
    //     CFSubjects, CFLicences, CFItemTypes, CFAssociationGroupings,
    //     and per-item InsertAsync for CFRubrics.
}
else
{
    if (cfDocumentCheck.lastChangeDateTime < CfPackage.CFDocument.lastChangeDateTime)
    {
        var cfItem = _cfPackage.WithDetailsAsync().Result
            .Include(x => x.CFItems)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFConcepts)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFSubjects)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFItemTypes)
            .Include(x => x.CFDefinitions).ThenInclude(x => x.CFLicences)
            .Include(x => x.CFDocument)
            .FirstOrDefault(x => x.CFDocument.Id == cfDocumentCheck.Id);
        await _cfPackage.UpdateAsync(cfItem, true);
    }
}
```

So:
- **First import of a document:** insert everything fresh.
- **Re-import of an existing document, older or equal `lastChangeDateTime`:**
  no-op.
- **Re-import of an existing document, newer `lastChangeDateTime`:** the
  code calls `_cfPackage.UpdateAsync(cfItem, true)` on the *existing*
  in-DB entity without applying any of the new data from `CfPackage` (which
  is, at this point in the code, still a freshly `new CFPackage()` with only
  FK Ids set — see line 107 `var CfPackage = new CFPackage();`). This is a
  bug: updates are detected but never applied. Practically the import is
  **insert-once, never-refresh** in the field.

No row-level idempotency keys beyond the `identifier` check. No deletes /
cleanup of stale items. No transactional boundary spanning the whole import
— each `InsertManyAsync` commits in its own UoW (the `true` second argument
forces an immediate save).

---

## 10. Triggering / scheduling

**Strictly on-demand from the admin UI.** No Hangfire / Quartz cron job for
IMS standards. The only background job mentioning "standard" in the LMS
codebase is `StandardImportBackgroundJob`
(`services/lms/host/EdvanceLS.LMS.HttpApi.Host/BackgroundJob/StandardImportBackgroundJob.cs`),
but inspection (lines 28-32) shows it imports an MCT content **zip file**
via `IMCTContentService.ImportFileMethod(args.zipFile)` — it is unrelated to
the IMS CASE Network. Confirmed by searching for `RemoteCaseNetwork` /
`Hangfire` / `RecurringJob` references across the service: none schedules the
IMS path.

Cadence in practice: whatever cadence the admin clicks the button. The Synapse
side's monthly `ScheduleTrigger` (per `legacy-standards-refresh.md`) merely
re-fetches whatever happens to be in the LMS DB at that moment.

---

## 11. Exact column mapping IMS → dim_standard

Combined table — single source of truth for the rebuild. Where the value is
literally a CFItem JSON field, that is shown; where it requires walking the
CFAssociations hierarchy, the level is named.

| `dim_standard` column | Where it comes from in the IMS CASE Network payload | Notes |
|---|---|---|
| `Identifier` | `CFItem.identifier` (lowercased by the LMS at line 223/279) | UUID v4 from IMS |
| `Language` | `CFItem.language` (lowercased) | e.g. `en_us` |
| `Schoology_Standard` | `CFItem.humanCodingScheme` | Misnamed — has nothing to do with Schoology. See Section 12. |
| `cPalms_Standard` | derived: `".".join(humanCodingScheme.split('.')[2:])` | Same code in `Standards_py.ipynb`. |
| `description` | `CFItem.fullStatement` | The actual benchmark text. |
| `cluster` | `CFAssociation.originNodeURI.title` at cluster depth (3rd level under document) | Display title of the cluster node. |
| `Subject` | `CFDocument.subject[0]` | First entry of the `List<string>`. |
| `Grader` | `CFAssociation.originNodeURI.title` at grade-level depth (1st level under document) | e.g. `"Kindergarten"`. |
| `Strand` | `CFAssociation.originNodeURI.title` at strand depth (2nd level under document) | e.g. `"Historical and Global Connections"`. |
| `Cognitive_Complexity_Rating` | not in IMS payload | Hardcoded `''` by Standards_py. Should be sourced elsewhere (FLDOE's cPALMS HTML pages carry it, but the IMS feed strips it). |
| `lastChangeDateTime` | `CFItem.lastChangeDateTime` | ISO-8601 in IMS, but coerced to .NET `DateTime.ToString()` (US-locale `M/d/yyyy h:mm:ss tt`) by the LMS — see `LocalCaseNetworkStandards.cs:224`. |
| `Direct_Link` | `CFDocument.uri` | The *document*'s URI, not the item's — so every standard from the same framework shares one link. |
| `Standard_New` | derived: `".".join(humanCodingScheme.split('.')[4:])` | Shortest code. |

`Custom.CleanedDescription` and `uniquesID` columns in the current
`dim_standard.csv` are downstream artifacts (Synapse Schoology preprocess
applies `clean_dataset` and concatenates `Identifier + '_' + Schoology_Standard`).
`rundate` is the Synapse landing run timestamp. None of these need to be
sourced from IMS.

**Walking the tree.** The leaf depth at which a row becomes a `dim_standard`
record is the 4th nested `children[]` level in the `/local-standards` response,
which corresponds to the 4th depth in the CFAssociations DAG below the
CFDocument node:

```
CFDocument (subject, uri)
  └─ CFAssociation → CFItem of CFItemType "Grade"   ← Grader (originNodeURI.title)
       └─ CFAssociation → CFItem of CFItemType "Strand"   ← Strand
            └─ CFAssociation → CFItem of CFItemType "Cluster"   ← cluster
                 └─ CFAssociation → CFItem of CFItemType "Standard" / "Benchmark"   ← row
                       (title=HumanCodingScheme, description=FullStatement, identifier=Identifier, ...)
```

For frameworks that don't follow this exact 4-level taxonomy (some CASE
documents have fewer levels), the legacy `Standards_py` will throw a
`KeyError` on the deepest `children`. The implementation has no
defensive depth-check.

---

## 12. What's "Schoology_Standard" doing in here if the source is IMS?

**Misnaming, full stop.** The value in the `Schoology_Standard` column is
`CFItem.humanCodingScheme` (e.g. `"VA.K.H.2.1"`, `"MA.K.NSO.1.1"`,
`"SS.K.A.1.2"`). This is the FLDOE-published cPALMS standard code as it
appears in the IMS payload. Schoology coincidentally uses the same code as
its own standard identifier when wired up to the same framework, which is
presumably why the original author named the column that way, but **no API
call to Schoology is involved at any point** in producing this column —
verified by:

1. The only writer of `lms_raw/v{version}/standards/standards.json` in the
   notebook codebase is `Standards_py.load_standard()`, which does no
   Schoology HTTP at all.
2. The C# import path
   (`RemoteCaseNetworkStandards.Import` → `importCfDocument` →
   `GetCFPackage`) likewise never touches Schoology.
3. The Schoology notebook (`Schoology_py.ipynb`) has no
   `fetch_data('standards')` call.

If we choose to keep the column name for backwards compatibility with PBIX
measures (recommended: yes, to keep `dim_standard` joins stable in the
existing report), we should rename it conceptually in our internal docs to
`HumanCodingScheme` / `StandardCode`.

---

### Buildability assessment

**Yes — fully buildable directly from IMS, skipping EdvanceLearning entirely.**

We have:
- Confirmed endpoint base: `https://casenetwork.1edtech.org/ims/case/v1p1/`.
- Confirmed auth: OAuth2 client_credentials at
  `https://casenetwork.1edtech.org/case-oauth2/clienttoken` using HTTP Basic.
- Working credentials (committed in legacy appsettings) — but treat as
  compromised; we should request our own from 1EdTech, or use the public
  anonymous endpoint variant 1EdTech offers for the same hub.
- A 1:1 column map from the CASE response to every `dim_standard` field
  except `Cognitive_Complexity_Rating`, which is `''` in legacy too — so we
  can match legacy bit-for-bit with `'' ` and revisit later.
- An understanding of how to walk `CFAssociations` to build the 4-level
  tree (grade → strand → cluster → standard) without needing the LMS's
  `/local-standards` flattener.

There is no need to stand up the .NET LMS, no need to round-trip through
EdvanceLearning's auth server (`auth.edvancelearning.us/connect/token`), no
need for the IdentityServer / SQL Server / Blazor pieces. A standalone Python
script can replicate everything.

The only thing that **isn't** in the IMS feed and needs to come from another
source (or stay blank) is `Cognitive_Complexity_Rating`. Legacy treats it as
empty; we can do the same to start.

### Recommended architecture for our mirror

A standalone Python refresh script that pulls from IMS directly and writes
`supabase/seeds/dim_standard.csv` in place.

- **Script path:** `supabase/seeds/refresh_standards.py` (overwrite the
  existing one, which is currently mis-documented as hitting Schoology).
- **Auth method:** OAuth2 client_credentials via HTTP Basic, mirroring
  `ImsCaseNetworkApiCall` in `RemoteCaseNetworkStandards.cs:619-651`.
- **Configuration shape (env vars):**
  - `IMS_CASE_BASE_URL` (default `https://casenetwork.1edtech.org/ims/case/v1p1/`)
  - `IMS_CASE_TOKEN_URL` (default `https://casenetwork.1edtech.org/case-oauth2/clienttoken`)
  - `IMS_CASE_CLIENT_ID`
  - `IMS_CASE_CLIENT_SECRET`
  - `IMS_CASE_DOCUMENT_IDS` (comma-separated CFDocument identifier
    whitelist, or `all`. Replaces the Blazor checkbox UI.)
- **Pagination strategy:** none (matches legacy). One GET per CFPackage. If
  1EdTech ever changes that, add `Link`-header parsing.
- **Tree walking:** rebuild grade→strand→cluster→standard locally from
  `CFPackage.CFAssociations` instead of going via `/local-standards`. Group
  associations by `destinationNodeURI.identifier` and recurse from the
  CFDocument root. Stop at the depth where `CFItem.CFItemTypeURI.title`
  matches a "Standard"/"Benchmark"/"Item" pattern, or simply at any leaf
  (a node that is never a `destinationNodeURI` of another association).
- **Output strategy:** **write the CSV directly.** No staging in Postgres.
  Rationale: `supabase/seeds/dim_standard.csv` is already the canonical
  artifact for the seed loader (`load_standards.py`), and round-tripping
  through Postgres adds complexity without gain. Use a temp file +
  `os.replace()` for atomicity. Run as a one-shot CLI; gate by a `--dry-run`
  flag to preview the diff against the current CSV.
- **Idempotency:** the script regenerates the CSV from scratch each run
  (full replace), so no "merge" logic is needed. Commit the resulting CSV
  to git for review — diffs will be small as IMS data is stable.
- **Error handling:** add `tenacity`-style retry on the token + CFPackage
  GETs (5 attempts, exponential backoff, respect `Retry-After`) — directly
  addresses the legacy's no-retry weakness.
- **Schema validation:** Pydantic models for the inbound JSON, panic on
  schema drift rather than silently dropping fields.
- **Logging:** structlog / stdlib logging at INFO per CFDocument processed;
  WARN on missing levels; ERROR on auth/HTTP failure.

This produces a faithful `dim_standard.csv` mirror in roughly 200 lines of
Python, with none of the legacy's latent bugs (`importCfDocument` not
awaited; updates detected but not applied; no token caching; no retries).
