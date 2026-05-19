"""
Parse Report/Layout JSON (UTF-16 LE inside the unpacked PBIX).
Enumerates pages, visuals, and `Table.Field` references via singleVisual.projections.*.queryRef.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

LAYOUT = Path(r"E:\Work\PS_P\Gains-platform\data\_pbix_unpacked\Report\Layout")
OUT = Path(r"E:\Work\PS_P\Gains-platform\data\_pbix_extract")

raw = LAYOUT.read_bytes()
text = raw.decode("utf-16-le", errors="replace").lstrip("﻿")
layout = json.loads(text)


def collect_query_refs(visual_config: dict) -> Counter[str]:
    """Pick up every Table.Field reference from a visual."""
    refs = Counter()
    sv = visual_config.get("singleVisual", {})
    for role, items in (sv.get("projections") or {}).items():
        if isinstance(items, list):
            for item in items:
                qr = item.get("queryRef") if isinstance(item, dict) else None
                if isinstance(qr, str):
                    refs[qr] += 1
    return refs


def collect_tables(visual_config: dict) -> set[str]:
    """Pull table aliases from prototypeQuery.From[].Entity."""
    tables = set()
    sv = visual_config.get("singleVisual", {})
    for src in (sv.get("prototypeQuery") or {}).get("From", []) or []:
        if isinstance(src, dict) and isinstance(src.get("Entity"), str):
            tables.add(src["Entity"])
    return tables


def visual_title(vc: dict) -> str:
    """Best-effort title extraction from visual config."""
    try:
        title_obj = vc["singleVisual"]["vcObjects"]["title"]
        for entry in title_obj:
            try:
                lit = entry["properties"]["text"]["expr"]["Literal"]["Value"]
                return re.sub(r"^'|'$", "", lit) if isinstance(lit, str) else ""
            except Exception:
                continue
    except Exception:
        pass
    return ""


pages = []
sections = layout.get("sections", [])
for s in sections:
    page_name = s.get("displayName") or s.get("name") or "(unnamed)"
    visuals = s.get("visualContainers", []) or []
    visual_summaries = []
    for v in visuals:
        try:
            vc = json.loads(v.get("config", "{}"))
        except Exception:
            vc = {}
        try:
            vfilters = json.loads(v.get("filters", "[]"))
        except Exception:
            vfilters = []
        sv = vc.get("singleVisual", {})
        vis_type = sv.get("visualType") or vc.get("name") or "(unknown)"
        refs = collect_query_refs(vc)
        tables = collect_tables(vc)
        visual_summaries.append({
            "type": vis_type,
            "title": visual_title(vc),
            "tables": sorted(tables),
            "fields": refs.most_common(),
            "filter_count": len(vfilters),
        })
    pages.append({
        "name": page_name,
        "ordinal": s.get("ordinal"),
        "size": f"{s.get('width','?')}x{s.get('height','?')}",
        "visual_count": len(visuals),
        "visuals": visual_summaries,
    })

(OUT / "20_pages.json").write_text(json.dumps(pages, indent=2), encoding="utf-8")

# Markdown summary, page by page
lines = ["# Pages & Visuals\n"]
for p in pages:
    lines.append(f"## {p['name']}  _(ord {p['ordinal']}, {p['size']}, {p['visual_count']} visuals)_\n")
    type_counter = Counter(v["type"] for v in p["visuals"])
    lines.append(f"_Visual types:_ " + ", ".join(f"{t}×{c}" if c > 1 else t for t, c in type_counter.most_common()) + "\n")
    for v in p["visuals"]:
        head = f"- **{v['type']}**"
        if v["title"]:
            head += f" — _{v['title']}_"
        lines.append(head)
        if v["tables"]:
            lines.append(f"  - tables: {', '.join(v['tables'])}")
        if v["fields"]:
            lines.append(f"  - fields: " + ", ".join(f"{n}×{c}" if c > 1 else n for n, c in v["fields"]))
        if v["filter_count"]:
            lines.append(f"  - filters: {v['filter_count']}")
    lines.append("")
(OUT / "20_pages.md").write_text("\n".join(lines), encoding="utf-8")

# Aggregated counters
all_tables = Counter()
all_fields = Counter()
fields_per_page: dict[str, Counter] = {}
for p in pages:
    pf = Counter()
    for v in p["visuals"]:
        all_tables.update(v["tables"])
        for f, c in v["fields"]:
            all_fields[f] += c
            pf[f] += c
    fields_per_page[p["name"]] = pf

(OUT / "21_top_fields.md").write_text(
    "# Field/Measure usage across all pages\n\n"
    + "## Tables, by visuals using them\n"
    + "\n".join(f"- {t}: {c}" for t, c in all_tables.most_common())
    + "\n\n## Fields/Measures, by reference count\n"
    + "\n".join(f"- {f}: {c}" for f, c in all_fields.most_common(120)),
    encoding="utf-8",
)

# Per-page field tables
per_page = {p: {"tables": [], "fields": fields_per_page[p].most_common()}
            for p in fields_per_page}
(OUT / "22_fields_per_page.json").write_text(
    json.dumps(per_page, indent=2), encoding="utf-8"
)

# Console summary
print(f"pages: {len(pages)}")
print(f"distinct fields: {len(all_fields)}")
print(f"top 15 fields:")
for f, c in all_fields.most_common(15):
    print(f"  {c:>4}× {f}")
print(f"\ntables, by visual usage:")
for t, c in all_tables.most_common():
    print(f"  {c:>3}× {t}")
print(f"\npages of interest:")
for p in pages:
    if "Question Response Analysis" in p["name"] or p["name"] == "Home":
        print(f"  - {p['name']}: {p['visual_count']} visuals, {len(fields_per_page[p['name']])} distinct fields")
