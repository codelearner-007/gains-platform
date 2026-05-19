# Pages & Visuals

## Standard Summary  _(ord 14, 320.0x240.0, 23 visuals)_

_Visual types:_ multiRowCard×6, card×5, basicShape×4, textbox×2, 2ca6d33504829e750a95, e712919d449c265390ee, 10c98baa69d0e9b906e0, barChart, clusteredBarChart, 8d6cc76fae14ecdc6090

- **multiRowCard** — _# of standard_
  - tables: Titles
  - fields: Titles.H3 - # of  questions
- **card** — _Description_
  - tables: dim_standard
  - fields: Min(dim_standard.Custom.CleanedDescription)
- **textbox** — _Text box_
- **multiRowCard** — _Standard_
  - tables: dim_standard
  - fields: dim_standard.cPalms_Standard
- **2ca6d33504829e750a95**
- **textbox**
- **multiRowCard**
  - tables: dim_standard
  - fields: dim_standard.blank
- **card**
  - tables: dim_standard
  - fields: Min(dim_standard.lastChangeDateTime)
- **e712919d449c265390ee**
- **basicShape**
- **basicShape**
- **multiRowCard**
  - tables: dim_subject
  - fields: dim_subject.Subject
- **multiRowCard**
  - tables: dim_subject
  - fields: dim_subject.Grade_no
- **10c98baa69d0e9b906e0**
- **barChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, dim_standard
  - fields: Measure.Grade_Average_Standard_Measure, dim_standard.cPalms_Standard
- **clusteredBarChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, cube_standard_summary, dim_standard
  - fields: Sum(cube_standard_summary.Total_Questions), dim_standard.cPalms_Standard, Measure.Incorrect_Grade_Average_Standard_Measure
- **8d6cc76fae14ecdc6090**
- **basicShape**
- **card**
  - tables: dim_standard
  - fields: dim_standard.blank
- **card**
  - tables: dim_standard
  - fields: Min(dim_standard.Strand)
- **multiRowCard**
  - tables: dim_standard
  - fields: dim_standard.blank
- **basicShape**
- **card**
  - tables: dim_standard
  - fields: dim_standard.blank

## Strand Summary  _(ord 15, 320.0x240.0, 24 visuals)_

_Visual types:_ multiRowCard×7, card×3, basicShape×3, barChart×2, columnChart×2, 37f0f48d6dc927d61479, textbox, 4a0e0aedd03c7d221ca3, d2d373f10348244a6b33, b45a8b9ed650cb0da334, clusteredBarChart, 555e8cb5cb39da5da08d

- **barChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, dim_standard
  - fields: Measure.Incorrect_Grade_Average_Standard_Measure, dim_standard.cPalms_Standard
- **multiRowCard** — _# of standard_
  - tables: Titles
  - fields: Titles.H3 - # of  questions
- **multiRowCard** — _# of standard_
  - tables: Titles
  - fields: Titles.H3 - # of standards
- **multiRowCard** — _Standard_
  - tables: dim_standard
  - fields: dim_standard.Strand
- **37f0f48d6dc927d61479**
- **textbox**
- **multiRowCard**
  - tables: dim_standard
  - fields: dim_standard.blank
- **card**
  - tables: dim_standard
  - fields: Min(dim_standard.lastChangeDateTime)
- **4a0e0aedd03c7d221ca3**
- **columnChart** — _Correct and Incorrect % by Standards_
  - tables: cube_standard_summary, dim_standard
  - fields: dim_standard.cPalms_Standard, Sum(cube_standard_summary.Percentage_InCorrect_Answers), Sum(cube_standard_summary.Grade_Average)
- **columnChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, dim_standard
  - fields: Measure.Grade_Average_Standard_Measure, dim_standard.cPalms_Standard
- **d2d373f10348244a6b33**
- **basicShape**
- **basicShape**
- **multiRowCard**
  - tables: dim_subject
  - fields: dim_subject.Subject
- **multiRowCard**
  - tables: dim_subject
  - fields: dim_subject.Grade_no
- **b45a8b9ed650cb0da334**
- **clusteredBarChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, dim_standard
  - fields: dim_standard.cPalms_Standard, Measure.Grade_Average_Standard_Measure
- **barChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, dim_standard
  - fields: dim_standard.cPalms_Standard, Measure.Incorrect_Grade_Average_Standard_Measure
  - filters: 2
- **555e8cb5cb39da5da08d**
- **card**
  - tables: dim_standard
  - fields: dim_standard.blank
- **multiRowCard**
  - tables: dim_standard
  - fields: dim_standard.blank
- **basicShape**
- **card**
  - tables: dim_standard
  - fields: dim_standard.blank

## QuestionView  _(ord 19, 320.0x240.0, 2 visuals)_

_Visual types:_ htmlContent443BE3AD55E043BF878BED274D3A6855×2

- **htmlContent443BE3AD55E043BF878BED274D3A6855**
  - tables: Measure
  - fields: Measure.FormattedString
- **htmlContent443BE3AD55E043BF878BED274D3A6855**
  - tables: Measure
  - fields: Measure.FormattedString

## Question Summary Report  _(ord 6, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Summary Report_
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_item, dim_subject
  - fields: dim_item.Item_ID, dim_item.Item_Name, dim_subject.Assessment_type, dim_subject.Grade, dim_subject.Session, dim_subject.Subject
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Question Summary Report - teacher subtotal  _(ord 7, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Summary Report - Teacher Subtotal_
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_item, dim_subject
  - fields: dim_item.Item_ID, dim_subject.Session, dim_subject.Assessment_type, dim_subject.Grade, dim_subject.Subject, dim_item.Item_Name
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Year To Date - Longitudinal Report  _(ord 8, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **textbox** — _Longitudinal Report - Year To Date_
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_subject
  - fields: dim_subject.Assessment_type, dim_subject.Subject, dim_subject.Session, dim_subject.Grade, dim_subject.School_ID
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Year To Date - Longitudinal Report 2  _(ord 9, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **textbox** — _Longitudinal Report - Year To Date 2_
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_subject
  - fields: dim_subject.Grade, dim_subject.Assessment_type, dim_subject.Session, dim_subject.Subject, dim_subject.School_ID
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Year To Date - Longitudinal Report 3  _(ord 10, 1280.0x720.0, 9 visuals)_

_Visual types:_ multiRowCard×4, actionButton×2, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Longitudinal Report - Year To Date 3_
- **actionButton**
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_subject
  - fields: dim_subject.Assessment_type, dim_subject.Grade, dim_subject.Session, dim_subject.Subject, dim_subject.School_ID
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Question Response Analysis  _(ord 11, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Response Analysis_
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: SchoolLogo_Parameter, Titles, cube_question_summary_overall, dim_item, dim_subject
  - fields: dim_item.assessment_date, dim_subject.Assessment_type, dim_item.Item_Name, dim_subject.Grade, SchoolLogo_Parameter.SchoolLogo_Parameter, dim_subject.Subject, cube_question_summary_overall.Subject_ID, Titles.H3 - Teachers
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Question Response Analysis by Teacher  _(ord 12, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Response Analysis - By Teacher_
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_item, dim_subject
  - fields: dim_item.Item_ID, dim_item.Item_Name, dim_subject.Grade, dim_subject.Subject, dim_subject.Assessment_type, dim_subject.Session
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Question Response Analysis by Standard and Teacher  _(ord 13, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Response Analysis - By Standard and Teacher_
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_item, dim_subject
  - fields: dim_item.Item_ID, dim_item.Item_Name, dim_subject.Grade, dim_subject.Subject, dim_subject.Assessment_type, dim_subject.Session
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Question Summary Report - header highlights  _(ord 16, 1280.0x720.0, 9 visuals)_

_Visual types:_ multiRowCard×4, actionButton×2, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Summary Report - header highlights_
- **actionButton**
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: dim_item, dim_subject
  - fields: dim_item.Item_ID, dim_item.Item_Name, dim_subject.Assessment_type, dim_subject.Grade, dim_subject.Session, dim_subject.Subject
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Question Summary Report redacted  _(ord 17, 1280.0x720.0, 9 visuals)_

_Visual types:_ multiRowCard×4, actionButton×2, textbox, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, rdlVisual

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Summary Report - names redacted_
- **actionButton**
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**
- **rdlVisual**
  - tables: cube_users_summary
  - fields: cube_users_summary.Grade, cube_users_summary.Item_ID, cube_users_summary.Item_Name, cube_users_summary.Subject, cube_users_summary.Session, cube_users_summary.Assessment_type

## Question Response Analysis redacted  _(ord 18, 1280.0x720.0, 8 visuals)_

_Visual types:_ multiRowCard×4, textbox, rdlVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, actionButton

- **multiRowCard**
  - tables: Titles
  - fields: Titles.H1 - Longitudinal
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Response Analysis - names redacted_
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **rdlVisual**
  - tables: Titles, cube_question_summary_overall, dim_item, dim_subject
  - fields: dim_item.assessment_date, dim_subject.Assessment_type, dim_item.Item_Name, dim_subject.Grade, dim_subject.Subject, cube_question_summary_overall.Subject_ID, Titles.H3 - Teachers
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**

## Home  _(ord None, 1280.0x720.0, 73 visuals)_

_Visual types:_ actionButton×27, slicer×9, bookmarkNavigator×5, advancedSlicerVisual×5, cardVisual×4, tableEx×3, textbox×2, pivotTable×2, clusteredBarChart×2, image, 1559a2b105361a0cc343, basicShape, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, db844137966ae0926530, 5cef5ce02628b71ab890, clusteredColumnChart, lineChart, eef4265a56e9ac67a3b5, columnChart, areaChart, shape, 33dcf5e70068c700d86a, hundredPercentStackedAreaChart

- **actionButton**
- **bookmarkNavigator**
- **slicer**
  - tables: Drill Through Report
  - fields: Drill Through Report.Type
- **actionButton**
- **bookmarkNavigator**
- **bookmarkNavigator**
- **slicer** — _Report Variation_
  - tables: Drill Through Report
  - fields: Drill Through Report.Report Short Name
  - filters: 1
- **slicer**
  - tables: Drill Through Report
  - fields: Drill Through Report.Report Catergory
- **image**
- **cardVisual**
  - tables: Titles
  - fields: Titles.__Title
- **cardVisual** — _My activity_
  - tables: dim_subject
  - fields: Min(dim_subject.Subject)
- **advancedSlicerVisual**
  - tables: dim_subject
  - fields: dim_subject.Grade
- **advancedSlicerVisual**
  - tables: dim_subject
  - fields: dim_subject.Subject
  - filters: 1
- **slicer** — _Academic Year_
  - tables: dim_subject
  - fields: dim_subject.Session
  - filters: 1
- **textbox**
- **tableEx** — _Assessments Summary_
  - tables: Measure, dim_item, dim_subject
  - fields: dim_subject.Grade, dim_item.assessment_date, dim_item.Item_Name, Measure.Total Student, Query1._Data Bar - Grade Average
  - filters: 3
- **textbox**
- **1559a2b105361a0cc343**
- **basicShape**
- **actionButton**
- **slicer**
  - tables: dim_subject
  - fields: dim_subject.Assessment_type
  - filters: 1
- **slicer**
  - tables: dim_item
  - fields: dim_item.Section_Instructors
  - filters: 1
- **actionButton**
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **advancedSlicerVisual**
  - tables: Products
  - fields: Products.Color, Min(Products.Color_sort)
- **advancedSlicerVisual**
  - tables: Assessments
  - fields: Assessments.Grade
- **advancedSlicerVisual** — _TYPE_
  - tables: Products
  - fields: Products.Product Category, Min(Products.Product Category)
- **cardVisual** — _Key Performance Indicators_
  - tables: Assessments, Sales Measures, Titles
  - fields: Min(Assessments.Subject), Titles.H3 - Teachers
- **bookmarkNavigator**
- **pivotTable** — _Sales points_
  - tables: Drillthrough_Pages, Key Measures, Sales Measures
  - fields: Key Measures.Grade Average, Drillthrough_Pages.Report Catergory, Drillthrough_Pages.Report Name
- **actionButton** — _This report serves as a reference to showcase various ways the new features can be applied._
- **slicer**
  - tables: Report Short Name
  - fields: Report Short Name.Type
- **cardVisual** — _My activity_
  - tables: dim_subject
  - fields: Min(dim_subject.Subject)
- **db844137966ae0926530**
- **5cef5ce02628b71ab890**
- **tableEx** — _Assessments Summary_
  - tables: Assessments, Key Measures, Questions Data, Standards, Titles
  - fields: Assessments.Grade, Titles.H3 - Assessment Date, Questions Data.Item Name, Standards.Short Strand, Key Measures.Total Standards, Key Measures.Total Questions, Key Measures._Data Bar - Grade Average
  - filters: 3
- **pivotTable** — _Avg by Strands_
  - tables: Assessments, Key Measures, Sales Measures, Standards
  - fields: Assessments.Grade, Standards.Short Strand, Key Measures.Total Students, Key Measures.Total Standards, Key Measures.Total Questions, Key Measures.Grade Min, Key Measures.Grade Max, Key Measures.Grade Average
  - filters: 8
- **clusteredColumnChart**
  - tables: Clustered chart, Color, Date
  - fields: Clustered chart.Clustered columns, Clustered chart.Legend, Color.Color, Date.Month
  - filters: 1
- **actionButton** — _Top Button ON_
- **lineChart**
  - tables: Clustered chart, Color, Date
  - fields: Color.Color, Date.Month, Clustered chart.Clustered columns, Clustered chart.Legend
  - filters: 1
- **actionButton** — _Down Gray Button OFF_
- **actionButton** — _Top Gray Button OFF_
- **actionButton** — _Down Button ON_
- **actionButton** — _1 Chart Green_
- **actionButton** — _1 Chart Grey_
- **actionButton** — _1 Table Green_
- **actionButton** — _1 Table Grey_
- **clusteredBarChart**
  - tables: Assessments, Key Measures, Standards
  - fields: Assessments.Grade, Standards.Short Strand, Key Measures.Grae Avg
- **eef4265a56e9ac67a3b5**
- **actionButton** — _Top Gray Button OFF_
- **actionButton** — _Top Button ON_
- **actionButton** — _Down Gray Button OFF_
- **actionButton** — _Down Button ON_
- **columnChart**
  - tables: Date, Sales Measures
  - fields: Date.Month, Sales Measures.Rib_Ele_03, Sales Measures.Rib_Ele_01, Sales Measures.Rib_Ele_02, Sales Measures.Rib_Ele_04, Sales Measures.Rib_green_04, Sales Measures.Rib_green_01, Sales Measures.Rib_green_02, Sales Measures.Rib_green_03, Sales Measures.Rib_pink_01, Sales Measures.Rib_pink_02, Sales Measures.Rib_pink_03, Sales Measures.Rib_pink_04, Sales Measures.Rib_yellow_01, Sales Measures.Rib_yellow_02, Sales Measures.Rib_yellow_03, Sales Measures.Rib_yellow_04
- **areaChart**
  - tables: Date, Products, Sales Measures
  - fields: Date.Month, Sales Measures.Rib_purple_01 ★, Sales Measures.Rib_green_01 ★, Sales Measures.Rib_pink_01 ★, Sales Measures.Rib_yellow_01 ★, Products.Product Category
- **shape**
- **actionButton** — _Sort 1_
- **actionButton** — _Sort 2_
- **33dcf5e70068c700d86a**
- **actionButton** — _Top Gray Button OFF_
- **actionButton** — _Top Button ON_
- **actionButton** — _Down Gray Button OFF_
- **actionButton** — _1 Chart Grey_
- **actionButton** — _1 Table Green_
- **actionButton** — _Down Button ON_
- **actionButton** — _1 Table Grey_
- **actionButton** — _1 Chart Green_
- **clusteredBarChart** — _Grade Average by Assessment_
  - tables: Assessments, Key Measures, Questions Data
  - fields: Assessments.Grade, Questions Data.Item Name, Key Measures.Grae Avg, Key Measures.Total Students, Key Measures.Total Standards, Key Measures.Total Questions
- **hundredPercentStackedAreaChart**
  - tables: Date, Sales Measures
  - fields: Date.Month, Sales Measures.100%_blank, Sales Measures.100%_green_01 ★, Sales Measures.100%_green_02, Sales Measures.100%_green_03, Sales Measures.100%_green_04, Sales Measures.100%_pink_02, Sales Measures.100%_pink_03, Sales Measures.100%_pink_04, Sales Measures.100%_pink_01 ★, Sales Measures.100%_yellow_04, Sales Measures.100%_yellow_01 ★, Sales Measures.100%_yellow_02, Sales Measures.100%_yellow_03, Sales Measures.100%_purple_03, Sales Measures.100%_purple_04, Sales Measures.100%_purple_01 ★, Sales Measures.100%_purple_02
  - filters: 1
- **bookmarkNavigator**
- **slicer**
  - tables: Drill Through Report
  - fields: Drill Through Report.Sort 2
- **slicer** — _Report Variation_
  - tables: Report Short Name
  - fields: Report Short Name.Report Short Name
  - filters: 1
- **tableEx** — _Assessments Summary_
  - tables: Measure, dim_item, dim_strand, dim_subject
  - fields: dim_subject.Grade, dim_strand.Strand, Measure.Total Standard by Strand, Measure.Total Question Standard, Query1._Data Bar - Grade Average, dim_item.assessment_date, dim_item.Item_Name
  - filters: 4

## Standards Deep Dive interactive  _(ord 1, 1280.0x720.0, 39 visuals)_

_Visual types:_ card×7, actionButton×3, textbox×3, hundredPercentStackedBarChart×3, funnel×2, treemap×2, basicShape×2, clusteredBarChart×2, charticulatorVisualCommunity_VIEW×2, multiRowCard×2, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, tableEx, da6d5ecab89312157de5, a8d2ce8788ebecc45609, eba59b96c29ddb905415, barChart, 6035005a2e385d0ec112, 8856b8d1306803cda030, 0099551075094e5e0e30, 5aa4cb84362de031a83c, 6dbc92f024b199a41076

- **card** — _Instructor(s):_
  - tables: Titles
  - fields: Titles.Instructor(s):
- **card** — _Grade Average_
  - tables: Measure
  - fields: Measure.Grade_Average_Standard_Measure
- **card** — _Number of Standards_
  - tables: Measure
  - fields: Measure.Total Standard
- **card** — _Number of Questions_
  - tables: Measure
  - fields: Measure.Total Question
- **card** — _Total Students_
  - tables: Measure
  - fields: Measure.Total Student
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**
- **textbox** — _Standards Deep Dive_
- **actionButton**
- **funnel** — _Standards by # of Questions_
  - tables: Key Measures, Standards
  - fields: Key Measures.Total Questions, Standards.Standard, Key Measures.% of Correct Answers
- **treemap**
  - tables: Key Measures, Standards
  - fields: Standards.Short Strand, Key Measures.Total Questions, Standards.Standard
- **treemap** — _# of Standards by Strand_
  - tables: Measure, dim_standard
  - fields: dim_standard.Strand, Measure.Total Question Strand
  - filters: 6
- **actionButton**
- **tableEx**
  - tables: Key Measures, Standards, Standards related measures
  - fields: Standards.Schoology Short Standard, Key Measures.% of Correct Answers, Key Measures.% of Incorrect Choice, Key Measures.Total Questions, Standards related measures.No. of Sub Standards
- **da6d5ecab89312157de5**
- **card** — _Overall Lowest %_
  - tables: Key Measures
  - fields: Key Measures.% of Correct Answers
  - filters: 1
- **card** — _Overall Highest %_
  - tables: Key Measures
  - fields: Key Measures.% of Correct Answers
  - filters: 1
- **a8d2ce8788ebecc45609**
- **basicShape**
- **textbox**
- **eba59b96c29ddb905415**
- **barChart** — _Correct and Incorrect % by Standards_
  - tables: Key Measures, Standards
  - fields: Key Measures.% of Correct Answers, Key Measures.Total Questions, Standards.Standard
- **clusteredBarChart** — _Correct and Incorrect % by Standards_
  - tables: Key Measures, Standards
  - fields: Key Measures.Total Questions, Key Measures.% of Incorrect Choice, Standards.Standard
- **6035005a2e385d0ec112**
- **funnel** — _Standards by # of Questions_
  - tables: Key Measures, Standards
  - fields: Key Measures.Total Questions, Standards.Standard
- **clusteredBarChart** — _._
  - tables: Key Measures, Standards, Standards related measures
  - fields: Standards.Standard, Key Measures.Total Questions, Standards related measures.No. of Sub Standards
- **8856b8d1306803cda030**
- **hundredPercentStackedBarChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, cube_standard_summary, dim_standard
  - fields: Sum(cube_standard_summary.Total_Questions), Measure.Grade_Average_Standard_Measure, Measure.Incorrect_Grade_Average_Standard_Measure, dim_standard.cPalms_Standard
  - filters: 3
- **0099551075094e5e0e30**
- **basicShape**
- **textbox**
- **5aa4cb84362de031a83c**
- **hundredPercentStackedBarChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, cube_standard_summary, dim_standard
  - fields: Sum(cube_standard_summary.Total_Questions), Measure.Grade_Average_Standard_Measure, Measure.Incorrect_Grade_Average_Standard_Measure, dim_standard.cPalms_Standard
  - filters: 3
- **6dbc92f024b199a41076**
- **hundredPercentStackedBarChart** — _Correct and Incorrect % by Standards_
  - tables: Measure, cube_standard_summary, dim_standard
  - fields: Sum(cube_standard_summary.Total_Questions), Measure.Grade_Average_Standard_Measure, Measure.Incorrect_Grade_Average_Standard_Measure, dim_standard.cPalms_Standard
  - filters: 5
- **charticulatorVisualCommunity_VIEW**
  - tables: Measure, dim_standard
  - fields: dim_standard.Strand, Measure.Total Standard, Measure.Grade_Average_Standard_Measure, Measure.Performance Color Strand, Measure.Total Question Strand
  - filters: 4
- **charticulatorVisualCommunity_VIEW**
  - tables: Measure, dim_standard
  - fields: dim_standard.cPalms_Standard×2, Measure.Total Standard, Measure.Performance Color Standard2, Measure.Total Question Standard, Measure.Grade_Average_Standard_Measure
  - filters: 3
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1

## Question Response Analysis Interactive  _(ord 2, 1280.0x720.0, 28 visuals)_

_Visual types:_ card×7, tableEx×3, multiRowCard×3, actionButton×2, textbox×2, cardVisual, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, hundredPercentStackedBarChart, slicer, treemap, funnel, d8767445735262b0b0c0, basicShape, 467d134060d51b7cae0e, barChart, clusteredBarChart

- **card** — _Instructor(s):_
  - tables: Titles
  - fields: Titles.Instructor(s):
- **card** — _Overall Lowest %_
  - tables: Measure
  - fields: Measure.Grade Min
- **card** — _Overall Highest %_
  - tables: Measure
  - fields: Measure.Grade Max
- **card** — _Grade Average_
  - tables: Measure
  - fields: Measure.Grade_Average_Standard_Measure
- **card** — _Number of Standards_
  - tables: Measure
  - fields: Measure.Total Standard
- **card** — _Number of Questions_
  - tables: Measure
  - fields: Measure.Total Question
- **card** — _Total Students_
  - tables: Measure
  - fields: Measure.Total Student
- **tableEx** — _  Correct % by Standards_
  - tables: Measure, cube_question_summary_overall
  - fields: cube_question_summary_overall.Standards, Measure.Total Question Standard, Measure.Grade_Average_Standard_Measure
  - filters: 1
- **tableEx**
  - tables: cube_question_summary_overall
  - fields: Sum(cube_question_summary_overall.Sorting Question_No), cube_question_summary_overall.questionDax, Sum(cube_question_summary_overall.Grade_Average), cube_question_summary_overall.__FirstFormatted_correct_, cube_question_summary_overall.__FirstFormatted_Incorrect_Choice_Details, cube_question_summary_overall.__FirstFormatted_Incorrect_Details_Name, cube_question_summary_overall.CombineStandardsColumn, cube_question_summary_overall.CombineDescriptionsColumn
  - filters: 11
- **cardVisual** — _Question Summary Report_
  - tables: dim_subject
  - fields: Min(dim_subject.Subject)
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **actionButton**
- **multiRowCard**
  - tables: Key Measures, Student Submissions
  - fields: Key Measures.Total Questions, Key Measures.Total Students, Key Measures.Score, Sum(Student Submissions.Points Possible), Key Measures.% of Correct Answers
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
  - filters: 1
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
  - filters: 1
- **textbox** — _Question Response Analysis_
- **hundredPercentStackedBarChart** — _Correct and Incorrect % by Standards_
  - tables: Key Measures, Questions Data
  - fields: Key Measures.% of Correct Answers, Key Measures.% of incorrect answer, Questions Data.Standards, Key Measures.Total Questions
- **slicer**
  - tables: Standards
  - fields: Standards.Short Strand
- **treemap**
  - tables: Key Measures, Standards
  - fields: Standards.Short Strand, Key Measures.Total Questions, Standards.Standard
- **tableEx** — _  Correct % by Strands_
  - tables: Measure, dim_standard
  - fields: dim_standard.Strand, Measure.Total Standard, Measure.Grade_Average_Standard_Measure
- **funnel** — _Standards by # of Questions_
  - tables: Key Measures, Standards
  - fields: Key Measures.Total Questions, Standards.Standard
- **actionButton**
- **d8767445735262b0b0c0**
- **basicShape**
- **textbox**
- **467d134060d51b7cae0e**
- **barChart** — _Correct and Incorrect % by Standards_
  - tables: Key Measures, Standards
  - fields: Key Measures.% of Correct Answers, Key Measures.Total Questions, Standards.Standard
- **clusteredBarChart** — _Correct and Incorrect % by Standards_
  - tables: Key Measures, Standards
  - fields: Key Measures.Total Questions, Key Measures.% of Incorrect Choice, Standards.Standard

## Selected Assessment  _(ord 3, 320.0x240.0, 1 visuals)_

_Visual types:_ cardVisual

- **cardVisual** — _Selected Assessment(s)_
  - tables: dim_subject
  - fields: Min(dim_subject.ShowHistorySubject)

## Selected Strand  _(ord 4, 320.0x240.0, 1 visuals)_

_Visual types:_ cardVisual

- **cardVisual** — _Selected Assessment(s)_
  - tables: dim_subject
  - fields: Min(dim_subject.Subject)

## Incorrect Answer Details  _(ord 5, 1280.0x720.0, 17 visuals)_

_Visual types:_ multiRowCard×6, tableEx×3, textbox×2, simpleImageEBC4593F96F1425FB3D84C5BF02B5075, card, pivotTable, shape, treemap, actionButton

- **tableEx**
  - tables: cube_question_summary_overall, dim_standard
  - fields: Sum(cube_question_summary_overall.Sorting Question_No), cube_question_summary_overall.questionDax, Sum(cube_question_summary_overall.Grade_Average), cube_question_summary_overall.__FirstFormatted_correct_, cube_question_summary_overall.__FirstFormatted_Incorrect_Choice_Details, cube_question_summary_overall.CombineDescriptionsColumn
  - filters: 10
- **simpleImageEBC4593F96F1425FB3D84C5BF02B5075**
  - tables: SchoolLogo_Parameter
  - fields: SchoolLogo_Parameter.SchoolLogo_Parameter
- **card** — _Description_
  - tables: SchoolName_Parameter
  - fields: Min(SchoolName_Parameter.SchoolName_Parameter)
- **pivotTable**
  - tables: Key Measures, Student Submissions
  - fields: Student Submissions.Answer Submission, Key Measures.Total Students, Key Measures.% of all answers, Key Measures.% Incorrect all, Key Measures.Possible Points, Key Measures.Total Possible, Key Measures.Total Incorrect Choices
  - filters: 2
- **tableEx**
  - tables: fact_student_submission
  - fields: fact_student_submission.Answer_Submission, fact_student_submission.# of students, fact_student_submission.test3
  - filters: 3
- **multiRowCard**
  - tables: Measure
  - fields: Measure.Total Incorrect Choices
  - filters: 1
- **shape**
- **multiRowCard**
  - tables: cube_question_summary
  - fields: cube_question_summary.Subject
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Assessment Type
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 Course and Unit
- **tableEx**
  - tables: fact_student_submission
  - fields: fact_student_submission.Answer_Submission, fact_student_submission.User_Name
  - filters: 2
- **multiRowCard**
  - tables: Titles
  - fields: Titles.Report Header
- **multiRowCard**
  - tables: Titles
  - fields: Titles.H2 - Question Details
- **textbox**
- **treemap**
  - tables: Key Measures, Student Submissions
  - fields: Student Submissions.Answer Submission, Key Measures.Total Students, Key Measures.% of all answers
  - filters: 1
- **textbox**
- **actionButton**
