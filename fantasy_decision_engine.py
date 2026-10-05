#!/usr/bin/env python3
import csv, io, json, math, random, re, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
ANALYSIS = DATA / "analysis"
HISTORY = DATA / "history"
ANALYSIS.mkdir(parents=True, exist_ok=True)
HISTORY.mkdir(parents=True, exist_ok=True)
LEAGUES = ["full_ppr_10_team", "half_ppr_12_team"]
MY_MANAGER = "ironlung27"
SEASON = 2026

def fetch_csv(url):
    req=urllib.request.Request(url,headers={"User-Agent":"sleeper-fantasy-bridge/3.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))

def num(x):
    try: return float(x or 0)
    except: return 0.0

def norm(s):
    return re.sub(r"[^a-z0-9]","",(s or "").lower())

def fantasy_points(row,ppr):
    return round(
        num(row.get("passing_yards"))*.04 + num(row.get("passing_tds"))*4 - num(row.get("interceptions"))*2 +
        num(row.get("rushing_yards"))*.1 + num(row.get("rushing_tds"))*6 +
        num(row.get("receiving_yards"))*.1 + num(row.get("receiving_tds"))*6 +
        num(row.get("receptions"))*ppr + num(row.get("fumbles_lost"))*-2, 2)

def load_nflverse():
    stats_url=f"https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{SEASON}.csv"
    sched_url="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
    try: stats=fetch_csv(stats_url)
    except Exception: stats=[]
    try: sched=fetch_csv(sched_url)
    except Exception: sched=[]
    return stats,sched

def build_stats_index(stats,ppr):
    grouped=defaultdict(list)
    for r in stats:
        if str(r.get("season"))!=str(SEASON): continue
        key=norm(r.get("player_display_name") or r.get("player_name"))
        if key: grouped[key].append(r)
    out={}
    for key,rows in grouped.items():
        rows.sort(key=lambda r:int(num(r.get("week"))))
        recent=rows[-3:]
        def s(k): return sum(num(x.get(k)) for x in recent)
        fps=[fantasy_points(x,ppr) for x in rows]
        last3=[fantasy_points(x,ppr) for x in recent]
        out[key]={
            "games":len(rows),"fantasy_points_total":round(sum(fps),2),
            "fantasy_points_per_game":round(sum(fps)/len(fps),2) if fps else 0,
            "last_3_fantasy_points":last3,
            "last_3_avg":round(sum(last3)/len(last3),2) if last3 else 0,
            "last_3_targets":s("targets"),"last_3_receptions":s("receptions"),
            "last_3_carries":s("carries"),"last_3_rush_yards":s("rushing_yards"),
            "last_3_rec_yards":s("receiving_yards"),
            "last_3_redzone_touches":s("rushing_tds")+s("receiving_tds"),
            "trend":round((sum(last3)/len(last3) if last3 else 0)-(sum(fps)/len(fps) if fps else 0),2),
        }
    return out

def schedule_map(rows,current_week):
    out=defaultdict(list)
    for r in rows:
        if str(r.get("season"))!=str(SEASON) or (r.get("game_type") not in ("REG",None,"")): continue
        w=int(num(r.get("week")))
        if w<=current_week: continue
        for team,opp in [(r.get("home_team"),r.get("away_team")),(r.get("away_team"),r.get("home_team"))]:
            if team: out[team].append({"week":w,"opponent":opp})
    for t in out: out[t].sort(key=lambda x:x["week"])
    return out

def player_enrich(p,stats_idx,sched):
    q=dict(p); st=stats_idx.get(norm(p.get("name")))
    q["performance"]=st
    q["upcoming_schedule"]=sched.get(p.get("team"),[])[:6]
    return q

def score_player(p):
    st=p.get("performance") or {}
    trend=st.get("trend",0); recent=st.get("last_3_avg",0)
    opp=(st.get("last_3_targets",0)+st.get("last_3_carries",0))/3
    injury_penalty=8 if p.get("injury_status") in ("IR","Out") else 3 if p.get("injury_status") else 0
    return round(recent + .35*trend + .18*opp - injury_penalty,2)

def league_analysis(label,payload,stats,sched_rows):
    ppr=1.0 if "full_ppr" in label else .5
    idx=build_stats_index(stats,ppr); week=int(payload["week"]); sched=schedule_map(sched_rows,week)
    rosters=[]
    for r in payload.get("rosters",[]):
        rr=dict(r)
        rr["players"]=[player_enrich(p,idx,sched) for p in r.get("players",[])]
        rr["starters"]=[player_enrich(p,idx,sched) for p in r.get("starters",[])]
        rr["roster_value"]=round(sum(score_player(p) for p in rr["players"]),2)
        rosters.append(rr)
    me=next((r for r in rosters if (r.get("manager") or "").lower()==MY_MANAGER.lower()),None)
    free=[player_enrich(p,idx,sched) for p in payload.get("free_agents",[])]
    for p in free: p["decision_score"]=score_player(p)
    waiver=sorted(free,key=lambda p:p["decision_score"],reverse=True)[:75]

    lineup=[]
    if me:
        bypos=defaultdict(list)
        for p in me["players"]:
            bypos[p.get("position")].append(p)
        for pos,ps in bypos.items():
            ps.sort(key=score_player,reverse=True)
            lineup.append({"position":pos,"ranked_players":[{"name":p.get("name"),"score":score_player(p),"performance":p.get("performance"),"schedule":p.get("upcoming_schedule")} for p in ps]})

    trade=[]
    if me:
        my_positions=defaultdict(list)
        for p in me["players"]: my_positions[p.get("position")].append(p)
        for other in rosters:
            if other["roster_id"]==me["roster_id"]: continue
            op=defaultdict(list)
            for p in other["players"]: op[p.get("position")].append(p)
            for pos in ("RB","WR","TE"):
                mine=sorted(my_positions[pos],key=score_player,reverse=True)
                theirs=sorted(op[pos],key=score_player,reverse=True)
                if theirs and (not mine or score_player(theirs[0])>score_player(mine[0])+2):
                    trade.append({"manager":other.get("manager"),"position":pos,"target":theirs[0].get("name"),"target_score":score_player(theirs[0])})
    trade=sorted(trade,key=lambda x:x["target_score"],reverse=True)[:20]

    standings=[]
    for r in rosters:
        s=r.get("settings") or {}
        pf=num(s.get("fpts"))+num(s.get("fpts_decimal"))/100
        standings.append({"roster_id":r["roster_id"],"manager":r.get("manager"),"wins":s.get("wins",0),"losses":s.get("losses",0),"points_for":round(pf,2),"roster_value":r["roster_value"]})
    standings.sort(key=lambda x:(x["wins"],x["points_for"]),reverse=True)
    # Deterministic power index and rough playoff outlook, explicitly model-based.
    if standings:
        vals=[x["roster_value"] for x in standings]; lo,hi=min(vals),max(vals)
        for x in standings:
            strength=50 if hi==lo else 100*(x["roster_value"]-lo)/(hi-lo)
            x["power_index"]=round(.55*strength+.45*(100*(len(standings)-standings.index(x))/len(standings)),1)
            x["playoff_outlook_score"]=round(min(99,max(1,20+7*num(x["wins"])+.45*x["power_index"])),1)

    return {
      "generated_at":datetime.now(timezone.utc).isoformat(),"league":label,"week":week,
      "data_sources":{"league":"Sleeper","performance_schedule":"nflverse"},
      "my_roster_id":me.get("roster_id") if me else None,
      "waiver_rankings":waiver,"lineup_optimizer":lineup,"trade_targets":trade,
      "power_rankings":sorted(standings,key=lambda x:x["power_index"],reverse=True),
      "playoff_note":"playoff_outlook_score is a heuristic strength indicator, not a calibrated probability."
    }

def main():
    stats,schedules=load_nflverse()
    summary={"generated_at":datetime.now(timezone.utc).isoformat(),"season":SEASON,"leagues":{}}
    for label in LEAGUES:
        p=DATA/f"{label}.json"
        if not p.exists(): continue
        payload=json.loads(p.read_text(encoding="utf-8"))
        result=league_analysis(label,payload,stats,schedules)
        out=ANALYSIS/f"{label}_decision_engine.json"
        out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        weekdir=HISTORY/label; weekdir.mkdir(parents=True,exist_ok=True)
        (weekdir/f"week-{payload['week']}.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        summary["leagues"][label]={"decision_engine":str(out.relative_to(Path(__file__).resolve().parent))}
    (ANALYSIS/"decision_engine_index.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
