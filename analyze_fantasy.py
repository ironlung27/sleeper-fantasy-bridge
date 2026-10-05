
import json
from pathlib import Path
from datetime import datetime, timezone

DATA = Path(__file__).resolve().parent / "data"
ANALYSIS = DATA / "analysis"
HISTORY = DATA / "history"
ANALYSIS.mkdir(parents=True, exist_ok=True)
HISTORY.mkdir(parents=True, exist_ok=True)

LEAGUES = ["full_ppr_10_team", "half_ppr_12_team"]

def roster_map(payload):
    out = {}
    for r in payload.get("rosters", []):
        for p in r.get("players", []):
            out[str(p["player_id"])] = {
                "roster_id": r["roster_id"],
                "manager": r.get("manager"),
                "player": p,
            }
    return out

def previous_week_payload(label, week):
    if week <= 1:
        return None
    p = HISTORY / label / f"week-{week-1}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None

def analyze(label):
    current_path = DATA / f"{label}.json"
    payload = json.loads(current_path.read_text(encoding="utf-8"))
    week = int(payload["week"])
    prev = previous_week_payload(label, week)

    current = roster_map(payload)
    old = roster_map(prev) if prev else {}
    changes = []
    for pid in sorted(set(current) | set(old)):
        before, after = old.get(pid), current.get(pid)
        if before and not after:
            changes.append({"type":"drop","player":before["player"],"from_roster":before["roster_id"],"from_manager":before["manager"]})
        elif after and not before:
            changes.append({"type":"add","player":after["player"],"to_roster":after["roster_id"],"to_manager":after["manager"]})
        elif before and after and before["roster_id"] != after["roster_id"]:
            changes.append({"type":"roster_change","player":after["player"],"from_roster":before["roster_id"],"to_roster":after["roster_id"]})

    standings = []
    for r in payload.get("rosters", []):
        s = r.get("settings") or {}
        pf = (s.get("fpts", 0) or 0) + (s.get("fpts_decimal", 0) or 0) / 100
        standings.append({
            "roster_id": r["roster_id"],
            "manager": r.get("manager"),
            "team_name": r.get("team_name"),
            "wins": s.get("wins",0), "losses": s.get("losses",0), "ties": s.get("ties",0),
            "points_for": pf,
            "waiver_position": s.get("waiver_position"),
            "waiver_budget_used": s.get("waiver_budget_used",0),
        })
    standings.sort(key=lambda x:(x["wins"], x["points_for"]), reverse=True)

    by_id = {r["roster_id"]: r for r in payload.get("rosters", [])}
    scouting = []
    for r in payload.get("rosters", []):
        opps = (r.get("current_matchup") or {}).get("opponent_roster_ids") or []
        scouting.append({
            "roster_id": r["roster_id"], "manager": r.get("manager"),
            "opponents": [{
                "roster_id": oid,
                "manager": by_id.get(oid,{}).get("manager"),
                "team_name": by_id.get(oid,{}).get("team_name"),
                "starters": by_id.get(oid,{}).get("starters",[]),
                "players": by_id.get(oid,{}).get("players",[]),
            } for oid in opps]
        })

    analysis = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league": label, "week": week,
        "roster_changes_vs_previous_week": changes,
        "waiver_watch": sorted(payload.get("available_trending_adds",[]), key=lambda x:x.get("trend_count") or 0, reverse=True),
        "standings_power_input": standings,
        "opponent_scouting": scouting,
    }
    (ANALYSIS / f"{label}.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")

    week_dir = HISTORY / label
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / f"week-{week}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

for league in LEAGUES:
    analyze(league)
