"""Extract every visual on the SDD page into a clean summary.

Reads `_layout.full.json`, walks pages, finds the "Standards Deep Dive interactive"
section, then dumps each visualContainer's: position, visualType (or group),
queryRefs, conditional formatting (backColor expressions), filters, and
parentGroupName.
"""
import json
import re
from pathlib import Path

p = Path(__file__).parent / "_layout.full.json"
data = json.loads(p.read_text(encoding="utf-16-le", errors="replace") if False else p.read_text(encoding="utf-8"))

target = None
for sec in data["sections"]:
    if sec.get("displayName") == "Standards Deep Dive interactive":
        target = sec
        break

assert target is not None
print(f"# SDD page found: id={target['id']} name={target.get('name')}")
print(f"canvas: {target['width']} x {target['height']}")
print(f"page-level filters: {target.get('filters')}")
print(f"visualContainers: {len(target['visualContainers'])}")
print()

for i, vc in enumerate(target["visualContainers"]):
    cfg = json.loads(vc["config"])
    name = cfg.get("name")
    pos = (vc.get("x"), vc.get("y"), vc.get("z"), vc.get("width"), vc.get("height"))
    print(f"=== #{i} name={name} pos={pos}")

    if "singleVisualGroup" in cfg:
        g = cfg["singleVisualGroup"]
        print(f"   GROUP displayName={g.get('displayName')} hidden={g.get('isHidden')}")
        continue

    sv = cfg.get("singleVisual", {})
    vt = sv.get("visualType")
    disp = sv.get("display", {}) or {}
    is_hidden = disp.get("mode") == "hidden"
    print(f"   visualType: {vt} hidden={is_hidden}")
    parent = cfg.get("parentGroupName")
    if parent:
        print(f"   parentGroupName: {parent}")

    # Title
    vco = sv.get("vcObjects", {}) or {}
    title_obj = vco.get("title", [{}])[0].get("properties", {}) if vco.get("title") else {}
    title_text = None
    if title_obj.get("text"):
        try:
            title_text = title_obj["text"]["expr"]["Literal"]["Value"]
        except Exception:
            pass
    if title_text:
        print(f"   title: {title_text}")

    # query refs
    proj = sv.get("projections", {}) or {}
    for role, items in proj.items():
        for it in items:
            print(f"   projection[{role}]: {it.get('queryRef')}")

    # Look for prototypeQuery selects (with measures/columns)
    pq = sv.get("prototypeQuery", {}) or {}
    if pq.get("From"):
        froms = [(x.get("Name"), x.get("Entity")) for x in pq["From"]]
        print(f"   from: {froms}")
    for s in pq.get("Select", []) or []:
        for k in ("Measure", "Column", "Aggregation"):
            if k in s:
                e = s[k]
                if k == "Aggregation":
                    inner = e.get("Expression", {}).get("Column", {})
                    print(f"   select Aggregation(fn={e.get('Function')}): {inner.get('Property')}")
                else:
                    print(f"   select {k}: {e.get('Property')} alias={s.get('Name')}")
        if "NativeReferenceName" in s:
            print(f"   nativeRefName: {s.get('NativeReferenceName')}")

    # Look for conditional formatting (backColor expressions referencing Measure)
    objs = sv.get("objects", {}) or {}
    for ok, ovs in objs.items():
        for ov in (ovs or []):
            props = ov.get("properties", {}) or {}
            sel = ov.get("selector")
            if "backColor" in props:
                bc = props["backColor"]
                if isinstance(bc, dict):
                    sj = json.dumps(bc)
                    # match measure refs
                    m = re.search(r'"Property":"([^"]+)"', sj)
                    if m:
                        print(f"   COND-FMT backColor[{ok}] sel={sel} measure={m.group(1)}")
                    else:
                        # literal color?
                        m2 = re.search(r"#[0-9A-Fa-f]{6}", sj)
                        if m2:
                            print(f"   COND-FMT backColor[{ok}] literal={m2.group(0)}")
            if ok == "dataPoint":
                # bar/treemap/funnel data colors
                sj = json.dumps(props)
                m = re.search(r'"Property":"([^"]+)"', sj)
                if m:
                    print(f"   DATAPOINT-COLOR via measure={m.group(1)} sel={sel}")
                else:
                    m2 = re.search(r"#[0-9A-Fa-f]{6}", sj)
                    if m2:
                        print(f"   DATAPOINT-COLOR literal={m2.group(0)} sel={sel}")
            # specifically capture fill rules / data colors of charts
            if ok in ("treemap", "funnel", "barChart", "categoryAxis", "labels"):
                pass

    # Visual-level filters
    vc_filters = vc.get("filters")
    if vc_filters and vc_filters != "[]":
        try:
            fl = json.loads(vc_filters)
            for f in fl:
                expr = f.get("expression", {})
                # find table/field
                inner = json.dumps(expr)
                m = re.search(r'"Entity":"([^"]+)".*?"Property":"([^"]+)"', inner)
                if m:
                    print(f"   filter[{f.get('type')}/{f.get('howCreated')}]: {m.group(1)}.{m.group(2)} hidden={f.get('isHiddenInViewMode')}")
                else:
                    print(f"   filter (no field): {f.get('type')}/{f.get('howCreated')}")
        except Exception as e:
            print(f"   filter parse error: {e}")
    print()
