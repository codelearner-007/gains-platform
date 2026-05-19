"""
Full PBIX extraction:
  - Tables and column schemas
  - DAX measures (with expressions)
  - Power Query M source code
  - Relationships
  - Row-level security (Roles + filter expressions)
  - Per-table statistics (row count, size)
  - Power BI metadata
Writes everything as text/JSON/CSV under data/_pbix_extract/ for inspection.
"""
from __future__ import annotations

import json
from pathlib import Path

from pbixray import PBIXRay

PBIX = Path(r"E:\Work\PS_P\Gains-platform\data\Assessment Analysis Dashboard.pbix")
OUT = Path(r"E:\Work\PS_P\Gains-platform\data\_pbix_extract")
OUT.mkdir(parents=True, exist_ok=True)


def write(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"  wrote {name} ({len(content):,} chars)")


def write_json(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {name}")


print(f"Opening: {PBIX.name} ({PBIX.stat().st_size / 1_048_576:.1f} MB)")
m = PBIXRay(str(PBIX))

# 1. metadata
print("\n[1] metadata")
try:
    write_json("01_metadata.json", m.metadata.to_dict(orient="records") if hasattr(m.metadata, "to_dict") else dict(m.metadata))
except Exception as e:
    write("01_metadata_error.txt", repr(e))

# 2. tables
print("\n[2] tables")
try:
    tables = list(m.tables)
    write_json("02_tables.json", tables)
    print(f"  {len(tables)} tables")
except Exception as e:
    write("02_tables_error.txt", repr(e))
    tables = []

# 3. schema (columns + types per table)
print("\n[3] schema")
try:
    schema = m.schema
    schema.to_csv(OUT / "03_schema.csv", index=False)
    print(f"  {len(schema)} columns total")
except Exception as e:
    write("03_schema_error.txt", repr(e))

# 4. DAX measures
print("\n[4] dax measures")
try:
    dax = m.dax_measures
    dax.to_csv(OUT / "04_dax_measures.csv", index=False)
    # Also write a readable .dax file
    lines = []
    for _, row in dax.iterrows():
        tbl = row.get("TableName", "")
        nm = row.get("Name", "")
        expr = row.get("Expression", "")
        desc = row.get("Description", "") or ""
        ff = row.get("FormatString", "") or ""
        lines.append(f"// table: {tbl}")
        if desc:
            lines.append(f"// description: {desc}")
        if ff:
            lines.append(f"// format: {ff}")
        lines.append(f"MEASURE [{nm}] =")
        lines.append(str(expr))
        lines.append("")
        lines.append("---")
        lines.append("")
    write("04_dax_measures.dax", "\n".join(lines))
    print(f"  {len(dax)} measures")
except Exception as e:
    write("04_dax_measures_error.txt", repr(e))

# 5. Calculated columns (DAX, separate from measures)
print("\n[5] calculated columns (DAX)")
try:
    cc = m.dax_columns
    cc.to_csv(OUT / "05_dax_columns.csv", index=False)
    lines = []
    for _, row in cc.iterrows():
        tbl = row.get("TableName", "")
        nm = row.get("ColumnName", "")
        expr = row.get("Expression", "")
        lines.append(f"// table: {tbl}")
        lines.append(f"COLUMN [{nm}] =")
        lines.append(str(expr))
        lines.append("")
        lines.append("---")
        lines.append("")
    write("05_dax_columns.dax", "\n".join(lines))
    print(f"  {len(cc)} calculated columns")
except Exception as e:
    write("05_dax_columns_error.txt", repr(e))

# 6. DAX tables (calculated tables)
print("\n[6] calculated tables (DAX)")
try:
    dt = m.dax_tables
    dt.to_csv(OUT / "06_dax_tables.csv", index=False)
    print(f"  {len(dt)} calculated tables")
except Exception as e:
    write("06_dax_tables_error.txt", repr(e))

# 7. Power Query M source
print("\n[7] power query (M)")
try:
    pq = m.power_query
    pq.to_csv(OUT / "07_power_query.csv", index=False)
    lines = []
    for _, row in pq.iterrows():
        nm = row.get("TableName", row.get("Name", ""))
        expr = row.get("Expression", "")
        lines.append(f"// query: {nm}")
        lines.append("/* M source */")
        lines.append(str(expr))
        lines.append("")
        lines.append("---")
        lines.append("")
    write("07_power_query.m", "\n".join(lines))
    print(f"  {len(pq)} M queries")
except Exception as e:
    write("07_power_query_error.txt", repr(e))

# 8. Relationships
print("\n[8] relationships")
try:
    rel = m.relationships
    rel.to_csv(OUT / "08_relationships.csv", index=False)
    print(f"  {len(rel)} relationships")
except Exception as e:
    write("08_relationships_error.txt", repr(e))

# 9. Statistics (row counts + size per table)
print("\n[9] statistics")
try:
    stats = m.statistics
    stats.to_csv(OUT / "09_statistics.csv", index=False)
    print(f"  {len(stats)} stats rows")
except Exception as e:
    write("09_statistics_error.txt", repr(e))

# 10. Per-table data dumps (head only — we just need column shape)
print("\n[10] sample rows per table (head 5)")
heads = {}
for t in tables:
    try:
        df = m.get_table(t)
        path = OUT / "tables" / f"{t}.head.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.head(5).to_csv(path, index=False)
        heads[t] = {"rows": len(df), "cols": list(df.columns)}
    except Exception as e:
        heads[t] = {"error": repr(e)}
write_json("10_table_heads.json", heads)

# 11. Model size summary
print("\n[11] model size")
try:
    sz = m.size  # bytes
    write("11_model_size.txt", f"{sz} bytes ({sz/1048576:.1f} MB)\n")
except Exception as e:
    write("11_model_size_error.txt", repr(e))

print("\nDONE.")
