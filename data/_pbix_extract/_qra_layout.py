"""
Extract every visual on the 'Question Response Analysis Interactive' page
with full position, size, type, formatting, fields. Output JSON for the
frontend-next-dev agent so it can faithfully replicate the layout.
"""
from __future__ import annotations

import json
from pathlib import Path

LAYOUT = Path(r"E:\Work\PS_P\Gains-platform\data\_pbix_unpacked\Report\Layout")
OUT = Path(r"E:\Work\PS_P\Gains-platform\data\_pbix_extract")

raw = LAYOUT.read_bytes()
text = raw.decode("utf-16-le", errors="replace").lstrip("﻿")
layout = json.loads(text)


def deep_strip(node, max_depth=20, depth=0):
    """Recursive shallow copy; trim deep blobs that aren't useful."""
    if depth > max_depth:
        return "<truncated>"
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in ("queryDataPoints", "fillCustom", "filters"):
                continue
            out[k] = deep_strip(v, max_depth, depth + 1)
        return out
    if isinstance(node, list):
        return [deep_strip(x, max_depth, depth + 1) for x in node]
    return node


def lit(x):
    """Unwrap PBIX Literal expression."""
    if isinstance(x, dict) and "Literal" in x:
        v = x["Literal"].get("Value")
        if isinstance(v, str):
            v2 = v.strip("'")
            if v.endswith("D") and v2.replace(".", "").isdigit():
                return float(v2)
            return v2
        return v
    return x


def get_object_props(vc_objects: dict) -> dict:
    """Flatten singleVisual.objects into {object_name: {prop: value}}."""
    out = {}
    for obj_name, entries in (vc_objects or {}).items():
        merged = {}
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                props = entry.get("properties", {}) or {}
                for k, v in props.items():
                    if isinstance(v, dict) and "expr" in v:
                        merged[k] = lit(v["expr"])
                    else:
                        merged[k] = v
        out[obj_name] = merged
    return out


for s in layout.get("sections", []):
    if (s.get("displayName") or s.get("name")) != "Question Response Analysis Interactive":
        continue

    page = {
        "name": s.get("displayName") or s.get("name"),
        "size": {"width": s.get("width"), "height": s.get("height")},
        "background": s.get("config"),
        "visuals": [],
    }

    for v in s.get("visualContainers", []):
        try:
            vc = json.loads(v.get("config", "{}"))
        except Exception:
            vc = {}
        sv = vc.get("singleVisual", {})
        layouts = vc.get("layouts", [])
        pos = layouts[0]["position"] if layouts else {}

        projections = sv.get("projections", {})
        proto = sv.get("prototypeQuery", {})
        froms = proto.get("From", [])
        selects = proto.get("Select", [])

        # Map alias → entity
        alias_to_entity = {f.get("Name"): f.get("Entity") for f in froms}

        # Resolve every selected field
        fields = []
        for sel in selects:
            entry = {"alias": sel.get("Name"), "native": sel.get("NativeReferenceName")}
            for kind in ("Measure", "Column", "Aggregation", "HierarchyLevel"):
                if kind in sel:
                    obj = sel[kind]
                    if kind == "Aggregation":
                        # Aggregation wraps an Expression which has Column/Measure
                        agg_func = obj.get("Function")  # 0=Sum,1=Avg,2=Count,...
                        ex = obj.get("Expression", {})
                        for k2 in ("Column", "Measure"):
                            if k2 in ex:
                                src = ex[k2].get("Expression", {}).get("SourceRef", {}).get("Source")
                                entry["agg_function_id"] = agg_func
                                entry["aggregated_kind"] = k2
                                entry["entity"] = alias_to_entity.get(src, src)
                                entry["property"] = ex[k2].get("Property")
                                break
                    else:
                        src = obj.get("Expression", {}).get("SourceRef", {}).get("Source")
                        entry["kind"] = kind
                        entry["entity"] = alias_to_entity.get(src, src)
                        entry["property"] = obj.get("Property")
                    break
            fields.append(entry)

        # Roles: which projection slot goes where (Values, Rows, Columns, Category, etc.)
        roles = {}
        for role_name, items in projections.items():
            if isinstance(items, list):
                roles[role_name] = [item.get("queryRef") for item in items if isinstance(item, dict)]

        objs = get_object_props(sv.get("objects", {}))
        title_text = (objs.get("title", {}) or {}).get("text")
        bg_color = (objs.get("background", {}) or {}).get("color")

        page["visuals"].append({
            "name": vc.get("name"),
            "position": {
                "x": pos.get("x"),
                "y": pos.get("y"),
                "z": pos.get("z"),
                "width": pos.get("width"),
                "height": pos.get("height"),
            },
            "type": sv.get("visualType") or vc.get("name") or "(unknown)",
            "title": title_text,
            "background_color": bg_color,
            "tables": list(set(alias_to_entity.values())),
            "roles": roles,
            "fields": fields,
            "objects": objs,
        })

    # Sort by Y then X for reading order
    page["visuals"].sort(key=lambda v: (v["position"]["y"] or 0, v["position"]["x"] or 0))

    (OUT / "30_qra_interactive.json").write_text(
        json.dumps(page, indent=2, default=str), encoding="utf-8"
    )
    print(f"wrote 30_qra_interactive.json with {len(page['visuals'])} visuals")
    break
