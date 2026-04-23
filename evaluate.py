"""AFF Evaluation Engine - Stage 2-5
Reads backups/AFF-Evals-LATEST.xlsx, generates:
  - docs/data.json     (dashboard feed)
  - docs/jury/*.html   (132 per-jury scorecards)
  - docs/master/*.html (66 master founder cards)
No API keys. Rule-based synthesis. Runs after every backup.
"""
import json, os, re, datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
SRC  = ROOT / "backups" / "AFF-Evals-LATEST.xlsx"
OUT  = ROOT / "docs"
(OUT / "jury").mkdir(parents=True, exist_ok=True)
(OUT / "master").mkdir(parents=True, exist_ok=True)

RATING_MAP = {"strongly agree":4,"agree":3,"borderline":2,"weak":1}
WEIGHTS = {"Char":0.30,"Mindset":0.25,"Behav":0.25,"Lens":0.20}

def r2n(v):
    if v is None: return None
    s = str(v).strip().lower()
    for k,n in RATING_MAP.items():
        if k in s: return n
    return None

def weighted_pct(scores):
    vals = [(scores.get(b), WEIGHTS[b]) for b in WEIGHTS]
    if any(v is None for v,_ in vals): return None
    return round(sum(v*w for v,w in vals) * 25, 1)

def load_rows():
    if not SRC.exists(): return []
    # try Evaluations sheet, else first sheet
    xl = pd.ExcelFile(SRC)
    sheet = "Evaluations" if "Evaluations" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(SRC, sheet_name=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        fid = str(r.get("Founder ID") or r.get("FounderID") or "").strip()
        if not fid or not fid.startswith("F"): continue
        rows.append({
            "jury":  str(r.get("Evaluator","")).strip(),
            "fid":   fid,
            "name":  str(r.get("Founder Name","")).strip(),
            "startup":str(r.get("Startup","")).strip(),
            "subgroup":str(r.get("Subgroup","")).strip(),
            "notes": {
                "Char":str(r.get("Char Notes","") or ""),
                "Mindset":str(r.get("Mindset Notes","") or ""),
                "Behav":str(r.get("Behav Notes","") or ""),
                "Lens":str(r.get("Lens Notes","") or ""),
            },
            "scores": {
                "Char":r2n(r.get("Char Rating")),
                "Mindset":r2n(r.get("Mindset Rating")),
                "Behav":r2n(r.get("Behav Rating")),
                "Lens":r2n(r.get("Lens Rating")),
            },
            "signal": str(r.get("Strongest Signal","") or ""),
            "doubt":  str(r.get("Biggest Doubt","") or ""),
            "three":  str(r.get("Three Words","") or ""),
            "shortlist": str(r.get("Shortlist","") or "").strip().upper(),
            "reason": str(r.get("Shortlist Reason","") or ""),
            "updated":str(r.get("Last Updated","") or ""),
        })
    return rows

def synth(ja, jb):
    """Rule-based unbiased synthesis of two juries."""
    strengths, concerns, contradictions = [], [], []
    for b in WEIGHTS:
        a, bb = ja["scores"].get(b), jb["scores"].get(b)
        if a and bb and abs(a-bb) >= 2:
            contradictions.append(f"{b}: {ja['jury']}={a} vs {jb['jury']}={bb}")
        avg = ((a or 0)+(bb or 0))/2
        if avg >= 3.5:
            strengths.append(f"{b} strong (avg {avg})")
        elif avg and avg <= 2:
            concerns.append(f"{b} weak (avg {avg})")
    for j in (ja, jb):
        if j["signal"]: strengths.append(f"{j['jury']}: {j['signal'][:140]}")
        if j["doubt"]:  concerns.append(f"{j['jury']}: {j['doubt'][:140]}")
    conf = 90 - 20*len(contradictions)
    return {
        "strengths": strengths[:4],
        "concerns":  concerns[:4],
        "contradictions": contradictions,
        "confidence": max(20, conf),
    }

def build():
    rows = load_rows()
    # group by founder
    by_f = {}
    for r in rows:
        by_f.setdefault(r["fid"], []).append(r)

    jury_cards, master_cards = [], []
    for r in rows:
        pct = weighted_pct(r["scores"])
        jury_cards.append({**r, "pct": pct})

    for fid, pair in by_f.items():
        if len(pair) < 1: continue
        ja = pair[0]; jb = pair[1] if len(pair)>1 else None
        bucket_rows = []
        for b in WEIGHTS:
            a = ja["scores"].get(b)
            bv = jb["scores"].get(b) if jb else None
            avg = round(((a or 0)+(bv or 0))/(2 if jb else 1),2) if (a or bv) else None
            delta = abs((a or 0)-(bv or 0)) if (a and bv) else 0
            bucket_rows.append({"bucket":b,"a":a,"b":bv,"avg":avg,"delta":delta,"flag":"SPLIT" if delta>=2 else "OK"})
        pa = weighted_pct(ja["scores"])
        pb = weighted_pct(jb["scores"]) if jb else None
        final = round(((pa or 0)+(pb or 0))/(2 if pb else 1),1) if (pa or pb) else None
        sl_a = ja["shortlist"]; sl_b = jb["shortlist"] if jb else ""
        if sl_a=="YES" and sl_b=="YES": consensus="STRONG SHORTLIST"
        elif sl_a=="NO" and sl_b=="NO": consensus="REJECT"
        elif not jb: consensus="SINGLE JURY"
        else: consensus="PANEL REVIEW"
        ai = synth(ja, jb) if jb else {"strengths":[ja["signal"]],"concerns":[ja["doubt"]],"contradictions":[],"confidence":50}
        master_cards.append({
            "fid":fid,"name":ja["name"],"startup":ja["startup"],"subgroup":ja["subgroup"],
            "jury_a":ja["jury"],"jury_b":jb["jury"] if jb else None,
            "buckets":bucket_rows,"pct_a":pa,"pct_b":pb,"final":final,
            "consensus":consensus,"ai":ai,
        })

    master_cards.sort(key=lambda x:(x["final"] or 0), reverse=True)
    data = {
        "generated": dt.datetime.utcnow().isoformat()+"Z",
        "jury_cards": jury_cards,
        "master_cards": master_cards,
        "counts": {"rows":len(rows),"founders":len(by_f)},
    }
    (OUT/"data.json").write_text(json.dumps(data, indent=2, default=str))
    print(f"[evaluate] {len(rows)} rows, {len(by_f)} founders -> docs/data.json")

if __name__ == "__main__":
    build()
