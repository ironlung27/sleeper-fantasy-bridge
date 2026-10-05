#!/usr/bin/env python3
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://api.sleeper.app/v1"
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)

# Both leagues from Ryan's setup.
LEAGUES = {
    "full_ppr_10_team": "1389130395563327488",
    "half_ppr_12_team": "1389736155972390912",
}

def get(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": "sleeper-fantasy-bridge/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def player_name(p):
    if not p:
        return None
    return p.get("full_name") or " ".join(
        x for x in [p.get("first_name"), p.get("last_name")] if x
    ) or None

def slim_player(pid, players):
    # Team defenses use IDs such as "GB", "BAL", etc.
    p = players.get(str(pid))
    if not p:
        return {"player_id": str(pid), "name": str(pid), "position": "DEF" if len(str(pid)) <= 3 else None}
    return {
        "player_id": str(pid),
        "name": player_name(p),
        "position": p.get("position"),
        "fantasy_positions": p.get("fantasy_positions"),
        "team": p.get("team"),
        "status": p.get("status"),
        "injury_status": p.get("injury_status"),
        "injury_body_part": p.get("injury_body_part"),
        "injury_notes": p.get("injury_notes"),
        "depth_chart_position": p.get("depth_chart_position"),
        "depth_chart_order": p.get("depth_chart_order"),
    }

def resolve_ids(ids, players):
    return [slim_player(x, players) for x in (ids or [])]

def build_league(label, league_id, nfl_state, players, trending_adds, trending_drops):
    league = get(f"/league/{league_id}")
    rosters = get(f"/league/{league_id}/rosters")
    users = get(f"/league/{league_id}/users")
    week = int(nfl_state.get("week") or league.get("settings", {}).get("leg") or 1)

    matchups = get(f"/league/{league_id}/matchups/{week}")
    transactions = get(f"/league/{league_id}/transactions/{week}")

    users_by_id = {str(u["user_id"]): u for u in users}
    rostered_ids = set()
    roster_rows = []

    matchup_by_roster = {m["roster_id"]: m for m in matchups}
    matchup_groups = {}
    for m in matchups:
        matchup_groups.setdefault(m.get("matchup_id"), []).append(m)

    for r in rosters:
        pids = [str(x) for x in (r.get("players") or [])]
        rostered_ids.update(pids)
        owner = users_by_id.get(str(r.get("owner_id")), {})
        m = matchup_by_roster.get(r["roster_id"], {})
        opponents = [
            x["roster_id"] for x in matchup_groups.get(m.get("matchup_id"), [])
            if x.get("roster_id") != r["roster_id"]
        ]
        roster_rows.append({
            "roster_id": r["roster_id"],
            "owner_id": r.get("owner_id"),
            "manager": owner.get("display_name"),
            "team_name": (owner.get("metadata") or {}).get("team_name"),
            "settings": r.get("settings"),
            "starters": resolve_ids(r.get("starters"), players),
            "reserve": resolve_ids(r.get("reserve"), players),
            "taxi": resolve_ids(r.get("taxi"), players),
            "players": resolve_ids(r.get("players"), players),
            "current_matchup": {
                "matchup_id": m.get("matchup_id"),
                "points": m.get("points"),
                "opponent_roster_ids": opponents,
            },
        })

    # Useful fantasy-relevant free-agent pool. This intentionally excludes
    # inactive/non-NFL entries and keeps normal fantasy positions + defenses.
    free_agents = []
    for pid, p in players.items():
        if str(pid) in rostered_ids:
            continue
        positions = p.get("fantasy_positions") or []
        if not any(pos in {"QB", "RB", "WR", "TE", "K"} for pos in positions):
            continue
        if not p.get("team"):
            continue
        free_agents.append(slim_player(pid, players))

    trend_add_ids = [str(x.get("player_id")) for x in trending_adds]
    trend_drop_ids = [str(x.get("player_id")) for x in trending_drops]
    trend_counts_add = {str(x.get("player_id")): x.get("count") for x in trending_adds}
    trend_counts_drop = {str(x.get("player_id")): x.get("count") for x in trending_drops}

    available_trending_adds = []
    for pid in trend_add_ids:
        if pid not in rostered_ids:
            row = slim_player(pid, players)
            row["trend_count"] = trend_counts_add.get(pid)
            available_trending_adds.append(row)

    available_trending_drops = []
    for pid in trend_drop_ids:
        if pid not in rostered_ids:
            row = slim_player(pid, players)
            row["trend_count"] = trend_counts_drop.get(pid)
            available_trending_drops.append(row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "league_id": league_id,
        "week": week,
        "league": league,
        "users": users,
        "rosters": roster_rows,
        "current_matchups_raw": matchups,
        "transactions_current_week": transactions,
        "available_trending_adds": available_trending_adds,
        "available_trending_drops": available_trending_drops,
        "free_agents": free_agents,
    }

def main():
    nfl_state = get("/state/nfl")

    # Sleeper recommends caching the all-players endpoint rather than calling it
    # repeatedly. This workflow runs infrequently enough to fetch it once/run.
    players = get("/players/nfl")
    trending_adds = get("/players/nfl/trending/add?lookback_hours=24&limit=100")
    trending_drops = get("/players/nfl/trending/drop?lookback_hours=24&limit=100")

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nfl_state": nfl_state,
        "leagues": {}
    }

    for label, league_id in LEAGUES.items():
        payload = build_league(
            label, league_id, nfl_state, players, trending_adds, trending_drops
        )
        filename = f"{label}.json"
        (OUT / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        index["leagues"][label] = {
            "league_id": league_id,
            "file": f"data/{filename}",
            "league_name": payload["league"].get("name"),
            "week": payload["week"],
        }

    (OUT / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(index, indent=2))

if __name__ == "__main__":
    main()
