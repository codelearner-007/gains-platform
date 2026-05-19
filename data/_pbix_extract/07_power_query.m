// query: cube_question_summary
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_cube_question_summary = Source{[Schema="dbo",Item="cube_question_summary"]}[Data]
in
    dbo_cube_question_summary

---

// query: cube_questionincorrectchoice_summary
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_cube_questionincorrectchoice_summary = Source{[Schema="dbo",Item="cube_questionincorrectchoice_summary"]}[Data],
    #"Filtered Rows" = Table.SelectRows(dbo_cube_questionincorrectchoice_summary, each ([Answer_Submission] <> null))
in
    #"Filtered Rows"

---

// query: cube_standard_summary
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_cube_standard_summary = Source{[Schema="dbo",Item="cube_standard_summary"]}[Data]
in
    dbo_cube_standard_summary

---

// query: dim_item
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_dim_item = Source{[Schema="dbo",Item="dim_item"]}[Data],
    #"Filtered Rows" = Table.SelectRows(dbo_dim_item, each ([Item_ID] <> null) and ([School_ID] = SchoolID)),
    #"Filtered Rows1" = Table.SelectRows(
    #"Filtered Rows",
    each not List.AnyTrue(
        List.Transform(
            Text.Split(if FilterExpression = null then "|" else FilterExpression, " | "), 
            (x) => Text.Contains([Item_Name], x, Comparer.OrdinalIgnoreCase)
        )
    )
),
    #"Changed Type" = Table.TransformColumnTypes(#"Filtered Rows1", {{"assessment_date", type date}}, "en-US")
in
    #"Changed Type"

---

// query: dim_subject
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_dim_subject = Source{[Schema="dbo",Item="dim_subject"]}[Data],
    #"Filtered Rows" = Table.SelectRows(dbo_dim_subject, each ([Subject_ID] <> null) and ([School_ID] = SchoolID)),
    #"Added Custom" = Table.AddColumn(#"Filtered Rows", "GradeSort", each if [Grade] = "Grade K" then "Grade 0" else [Grade]),
    #"Filtered Rows1" = Table.SelectRows(#"Added Custom", each ([Subject_ID] <> "6dc2c0d6390d497e4cdc75884ba54d44e55af5169563f2a21e80043acff6d2bb" and [Subject_ID] <> "639b701aa86164b61a9c0af7ee9af81bbceced349df98c6adbda3d7b2ffd25b2"))
in
    #"Filtered Rows1"

---

// query: dim_question_data
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_dim_question_data = Source{[Schema="dbo",Item="dim_question_data"]}[Data]
in
    dbo_dim_question_data

---

// query: dim_strand
/* M source */
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_dim_strand = Source{[Schema="dbo",Item="dim_strand"]}[Data],
    Custom1 = Table.SelectRows(dbo_dim_strand, each ([strand_ID] <> null))
in
    Custom1

---

// query: Measure
/* M source */
let
    Source = "__Title = ""Assessments Dashboard"""
in
    Source

---

// query: Report Short Name
/* M source */
let
    Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i45WCi5JzEtJLEopVnBJTS1QcMksS1XIzCtJLUpMLgGylXSwqcApCkSGRkDCkwgTDJVidaKVAktTi0sy8/MUglKLC/LzilMVHPMScyqLM4sVUA3BrZCQJMguYwxH4dVipBQbCwA=", BinaryEncoding.Base64), Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [Page = _t, #"Report Name" = _t, #"Report Category" = _t, Report = _t, Sort = _t, Type = _t, #"Report Short Name" = _t, #"Sort 2" = _t])
in
    Source

---

// query: fact_student_submission
/* M source */
let
    Source = Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"),
    ldb_dev_s3_schoology_v0p1 = Source{[Name="ldb_dev_s3_schoology_v0p1"]}[Data],
    dbo_fact_student_submission = ldb_dev_s3_schoology_v0p1{[Schema="dbo",Item="fact_student_submission"]}[Data]
in
    dbo_fact_student_submission

---

// query: dim_standard
/* M source */
let
    Source = Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"),
    ldb_dev_s3_schoology_v0p1 = Source{[Name="ldb_dev_s3_schoology_v0p1"]}[Data],
    dbo_dim_standard = ldb_dev_s3_schoology_v0p1{[Schema="dbo",Item="dim_standard"]}[Data],
    #"Filtered Rows" = Table.SelectRows(dbo_dim_standard, each ([Identifier] <> null)),
    #"Added Custom" = Table.AddColumn(#"Filtered Rows", "Custom", each Html.Table([description],{{"CleanedDescription",":root"}})),
    #"Expanded Custom" = Table.ExpandTableColumn(#"Added Custom", "Custom", {"CleanedDescription"}, {"Custom.CleanedDescription"})
in
    #"Expanded Custom"

---

// query: Titles
/* M source */
let
    Source = ""
in
    Source

---

// query: cube_grade_summary
/* M source */
let
    Source = Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"),
    ldb_dev_s3_schoology_v0p1 = Source{[Name="ldb_dev_s3_schoology_v0p1"]}[Data],
    dbo_cube_grade_summary = ldb_dev_s3_schoology_v0p1{[Schema="dbo",Item="cube_grade_summary"]}[Data]
in
    dbo_cube_grade_summary

---

// query: cube_school_summary
/* M source */
let
    Source = Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"),
    ldb_dev_s3_schoology_v0p1 = Source{[Name="ldb_dev_s3_schoology_v0p1"]}[Data],
    dbo_cube_school_summary = ldb_dev_s3_schoology_v0p1{[Schema="dbo",Item="cube_school_summary"]}[Data]
in
    dbo_cube_school_summary

---

// query: cube_question_summary_overall
/* M source */
let
    Source = Sql.Databases("syn-oea-prodtest2-ondemand.sql.azuresynapse.net"),
    ldb_dev_s3_schoology_v0p1 = Source{[Name="ldb_dev_s3_schoology_v0p1"]}[Data],
    dbo_cube_question_summary_overall = ldb_dev_s3_schoology_v0p1{[Schema="dbo",Item="cube_question_summary_overall"]}[Data],
    #"Trimmed Text" = Table.TransformColumns(
    dbo_cube_question_summary_overall,
    {{"Description", each Text.Combine(Html.Table(_, {{"Description", ":root"}})[Description], " "), type text}}
),
    #"Filtered Rows" = Table.SelectRows(#"Trimmed Text", each ([Question_No] <> null))
in
    #"Filtered Rows"

---

// query: Drill Through Report
/* M source */
let
    Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("rZRda8IwFIb/ysFrhdW6r0tHGQ7G2FpvRLyI9mAD/SJJB/77JVY726RpFC9K27zvyftATs56PfqpkAta5BBVWUbYAUIsCyZG4zsrnny+g/cLaxQelzfjXghgGJOdwLh/ZweLVL5Ihlz+NtZpl6al2ZAmkCCJkUFC90kqH8EtdBNY1O7F2W3lNJj9LqnRYycWSHaJrOHVVhSCpFbg5ckcSTMVKVqBDeZZF/jSc0qfHYFXSBgsCwiIQBn8WeR7KqqY5iT9r26tTuBYI+qartrqtccuxmoZgNd03HA2TO3put5EKeXJlD9t2ssh3x/I1/QmSinPpnxfb5YQeVnkHGEutzhw2urm+4ov2ggI5/oI0CqNV/xGl2kWvLrPAj11ezhfGDudo0+Kb5dO76EL15KHzlLFRoLkMWExyJcz69VFNVlPmacN/35vPRrOIocAsYSA/iLQXCCTByO/pc/g6F1VCOrqfTjsMNiN7U1uvw0qy9egrCV1N14xER3npUKZaSh9s2Wz+QM=", BinaryEncoding.Base64), Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [Page = _t, #"Report Name" = _t, #"Report Catergory" = _t, Report = _t, Sort = _t, Type = _t, #"Report Short Name" = _t, #"Sort 2" = _t]),
    #"Filtered Rows" = Table.SelectRows(Source, each ([Report Short Name] <> "Redacted"))
in
    #"Filtered Rows"

---

// query: SchoolName_Parameter
/* M source */
let
    Source = School_Name
in
    Source

---

// query: SchoolLogo_Parameter
/* M source */
let
    Source = SchoolLogo
in
    Source

---
