#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parent

refresh = root / "refresh_sleeper.py"
s = refresh.read_text(encoding="utf-8")

old = '    week = int(nfl_state.get("week") or league.get("settings", {}).get("leg") or 1)\n\n    matchups = get(f"/league/{league_id}/matchups/{week}")\n    transactions = get(f"/league/{league_id}/transactions/{week}")\n'
new = '    # Sleeper\'s week is the live scoring week. Keep it for results/transactions,\n    # but use a separate planning week for forward-looking fantasy decisions.\n    live_week = int(nfl_state.get("week") or league.get("settings", {}).get("leg") or 1)\n    now = datetime.now(timezone.utc)\n    season_type = str(nfl_state.get("season_type") or "regular").lower()\n\n    # On Monday the current fantasy slate is effectively decided except MNF,\n    # so begin planning the next week without corrupting current-week records.\n    planning_week = live_week\n    if season_type == "regular" and now.weekday() == 0 and live_week < 18:\n        planning_week = live_week + 1\n\n    matchups = get(f"/league/{league_id}/matchups/{live_week}")\n    transactions = get(f"/league/{league_id}/transactions/{live_week}")\n    planning_matchups = (\n        get(f"/league/{league_id}/matchups/{planning_week}")\n        if planning_week != live_week else matchups\n    )\n'
if old not in s:
    raise SystemExit("refresh_sleeper.py: expected week block not found; no changes made")
s = s.replace(old, new, 1)

old = '        "week": week,\n        "league": league,\n'
new = '        "week": live_week,\n        "live_week": live_week,\n        "planning_week": planning_week,\n        "league": league,\n'
if old not in s:
    raise SystemExit("refresh_sleeper.py: payload week block not found")
s = s.replace(old, new, 1)

old = '        "current_matchups_raw": matchups,\n        "transactions_current_week": transactions,\n'
new = '        "current_matchups_raw": matchups,\n        "planning_matchups_raw": planning_matchups,\n        "transactions_current_week": transactions,\n'
if old not in s:
    raise SystemExit("refresh_sleeper.py: matchup block not found")
s = s.replace(old, new, 1)

old = '            "week": payload["week"],\n        }\n'
new = '            "week": payload["week"],\n            "live_week": payload["live_week"],\n            "planning_week": payload["planning_week"],\n        }\n'
if old not in s:
    raise SystemExit("refresh_sleeper.py: index block not found")
s = s.replace(old, new, 1)
refresh.write_text(s, encoding="utf-8")

engine = root / "fantasy_decision_engine.py"
e = engine.read_text(encoding="utf-8")
old = 'idx=stats_index(stats,ppr); week=int(payload["week"]); sch=schedules(sched_rows,week)'
new = 'idx=stats_index(stats,ppr); live_week=int(payload.get("live_week",payload["week"])); week=int(payload.get("planning_week",live_week)); sch=schedules(sched_rows,week)'
if old not in e:
    raise SystemExit("fantasy_decision_engine.py: expected week line not found")
e = e.replace(old, new, 1)

old = '"league":label,"week":week,'
new = '"league":label,"week":week,"live_week":live_week,"planning_week":week,'
if old not in e:
    raise SystemExit("fantasy_decision_engine.py: output week line not found")
e = e.replace(old, new, 1)
engine.write_text(e, encoding="utf-8")

print("Patched refresh_sleeper.py and fantasy_decision_engine.py successfully.")
