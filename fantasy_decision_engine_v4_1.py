#!/usr/bin/env python3
import csv, io, json, re, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA=Path(__file__).resolve().parent/"data"; ANALYSIS=DATA/"analysis"; HISTORY=DATA/"history"
ANALYSIS.mkdir(parents=True,exist_ok=True); HISTORY.mkdir(parents=True,exist_ok=True)
LEAGUES=["full_ppr_10_team","half_ppr_12_team"]; MY_MANAGER="ironlung27"; SEASON=2026

def num(x):
    try:return float(x or 0)
    except:return 0.0
def norm(s): return re.sub(r"[^a-z0-9]","",(s or "").lower())
def clamp(x,a,b): return max(a,min(b,x))
def fetch_csv(url):
    req=urllib.request.Request(url,headers={"User-Agent":"sleeper-fantasy-bridge/4.1"})
    with urllib.request.urlopen(req,timeout=60) as r:return list(csv.DictReader(io.StringIO(r.read().decode())))
def fp(r,ppr):
    return num(r.get("passing_yards"))*.04+num(r.get("passing_tds"))*4-num(r.get("interceptions"))*2+num(r.get("rushing_yards"))*.1+num(r.get("rushing_tds"))*6+num(r.get("receiving_yards"))*.1+num(r.get("receiving_tds"))*6+num(r.get("receptions"))*ppr-num(r.get("fumbles_lost"))*2
def load_nflverse():
    try:s=fetch_csv(f"https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{SEASON}.csv")
    except:s=[]
    try:g=fetch_csv("https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv")
    except:g=[]
    return s,g
def stats_index(rows,ppr):
    d=defaultdict(list)
    for r in rows:
        if str(r.get("season"))==str(SEASON):
            k=norm(r.get("player_display_name") or r.get("player_name"))
            if k:d[k].append(r)
    out={}
    for k,rs in d.items():
        rs.sort(key=lambda x:int(num(x.get("week")))); recent=rs[-3:]; vals=[fp(x,ppr) for x in rs]; rv=vals[-3:]
        sm=lambda key:sum(num(x.get(key)) for x in recent)
        out[k]={"games":len(rs),"fppg":round(sum(vals)/len(vals),2),"last3_avg":round(sum(rv)/len(rv),2),
          "last3_points":[round(x,2) for x in rv],"targets":sm("targets"),"carries":sm("carries"),
          "receptions":sm("receptions"),"rush_yards":sm("rushing_yards"),"rec_yards":sm("receiving_yards"),
          "trend":round((sum(rv)/len(rv))-(sum(vals)/len(vals)),2)}
    return out
def schedules(rows,week):
    d=defaultdict(list)
    for r in rows:
        if str(r.get("season"))!=str(SEASON) or int(num(r.get("week")))<=week:continue
        w=int(num(r.get("week")))
        for t,o in ((r.get("home_team"),r.get("away_team")),(r.get("away_team"),r.get("home_team"))):
            if t:d[t].append({"week":w,"opponent":o})
    for t in d:d[t].sort(key=lambda x:x["week"])
    return d
def enrich(p,idx,sch):
    q=dict(p);q["performance"]=idx.get(norm(p.get("name")));q["upcoming_schedule"]=sch.get(p.get("team"),[])[:6];return q

def model(p,league_size,roster_need=0,replacement=0,qb_need=False):
    st=p.get("performance") or {}; games=int(st.get("games",0)); pos=p.get("position")
    # 25 production: recent scoring, damped for tiny samples
    confidence=clamp(games/3,0,1)
    prod=clamp(st.get("last3_avg",0)*1.35,0,25)*(.45+.55*confidence)
    # 25 opportunity: touches/targets matter more than TD spikes
    opp3=st.get("carries",0)+st.get("targets",0)
    opportunity=clamp((opp3/3)*1.35,0,25)
    # 20 role: Sleeper depth order, with strong QB2 penalty
    order=p.get("depth_chart_order")
    role={1:20,2:11,3:5}.get(order,8 if order else 10)
    if pos=="QB" and order and order>1: role*=.35
    if p.get("injury_status") in ("IR","Out"): role=0
    elif p.get("injury_status"): role*=.7
    # 15 roster fit: positional need passed from user's roster
    fit=clamp(7.5+roster_need,0,15)
    # 1-QB leagues have a deep replacement pool. Suppress extra QBs unless the roster actually needs one.
    if pos=="QB" and not qb_need: fit=min(fit,3.0)
    # 10 replacement value: scarcity stronger in 12-team leagues
    scarcity={"RB":1.25,"WR":1.05,"TE":1.1,"QB":.20,"K":.25,"DEF":.25}.get(pos,.5)
    repl=clamp(5+replacement+(league_size-10)*.65*scarcity,0,10)
    if pos=="QB" and not qb_need: repl=min(repl,3.0)
    # 5 schedule: neutral until defensive-quality model is available
    schedule=2.5
    trend=clamp(st.get("trend",0),-5,5)
    total=clamp(prod+opportunity+role+fit+repl+schedule+trend*.35,0,100)
    conf="HIGH" if games>=3 else "MEDIUM" if games==2 else "LOW"
    direction="RISING" if st.get("trend",0)>2 else "FALLING" if st.get("trend",0)<-2 else "STEADY"
    return {"overall":round(total,1),"production":round(prod,1),"opportunity":round(opportunity,1),
      "role":round(role,1),"roster_fit":round(fit,1),"replacement_value":round(repl,1),"schedule":schedule,
      "confidence":conf,"trend":direction,"games_sampled":games}

def league_analysis(label,payload,stats,sched_rows):
    ppr=1 if "full_ppr" in label else .5; league_size=10 if "10_team" in label else 12
    idx=stats_index(stats,ppr); week=int(payload["week"]); sch=schedules(sched_rows,week)
    rosters=[]
    for r in payload.get("rosters",[]):
        rr=dict(r);rr["players"]=[enrich(p,idx,sch) for p in r.get("players",[])];rr["starters"]=[enrich(p,idx,sch) for p in r.get("starters",[])];rosters.append(rr)
    me=next((r for r in rosters if (r.get("manager") or "").lower()==MY_MANAGER),None)
    counts=defaultdict(int)
    if me:
        for p in me["players"]:counts[p.get("position")]+=1
    ideal={"QB":1,"RB":5 if league_size==12 else 4,"WR":6 if league_size==12 else 5,"TE":2}
    qb_need = counts["QB"] < 1
    free=[enrich(p,idx,sch) for p in payload.get("free_agents",[])]
    # Baseline replacement from available players by position
    raw=defaultdict(list)
    for p in free:
        st=p.get("performance") or {};raw[p.get("position")].append(st.get("last3_avg",0))
    baselines={k:(sum(sorted(v,reverse=True)[:max(3,league_size//2)])/max(1,len(sorted(v,reverse=True)[:max(3,league_size//2)]))) for k,v in raw.items()}
    for p in free:
        need=clamp((ideal.get(p.get("position"),1)-counts[p.get("position")])*1.8,-4,6)
        recent=(p.get("performance") or {}).get("last3_avg",0)
        replacement=clamp((recent-baselines.get(p.get("position"),recent))*.35,-3,3)
        p["decision_model"]=model(p,league_size,need,replacement,qb_need)
    waiver=sorted(free,key=lambda p:p["decision_model"]["overall"],reverse=True)[:75]
    for i,p in enumerate(waiver):
        s=p["decision_model"]["overall"];p["recommendation"]="PRIORITY ADD" if s>=70 else "ADD" if s>=58 else "WATCH" if s>=45 else "DEEP STASH"
        p["waiver_rank"]=i+1
    lineup=[]
    if me:
        bp=defaultdict(list)
        for p in me["players"]:
            p["decision_model"]=model(p,league_size,0,0);bp[p.get("position")].append(p)
        for pos,ps in bp.items():
            ps.sort(key=lambda p:p["decision_model"]["overall"],reverse=True)
            lineup.append({"position":pos,"ranked_players":[{"name":p.get("name"),"model":p["decision_model"]} for p in ps]})
    trade=[]
    if me:
        mine=defaultdict(list)
        for p in me["players"]:p["decision_model"]=model(p,league_size);mine[p.get("position")].append(p)
        for other in rosters:
            if other["roster_id"]==me["roster_id"]:continue
            for p in other["players"]:
                if p.get("position") not in ("RB","WR","TE"):continue
                p["decision_model"]=model(p,league_size)
                mybest=max([x["decision_model"]["overall"] for x in mine[p.get("position")]],default=0)
                if p["decision_model"]["overall"]>mybest+4:trade.append({"manager":other.get("manager"),"target":p.get("name"),"position":p.get("position"),"model":p["decision_model"]})
    trade.sort(key=lambda x:x["model"]["overall"],reverse=True)
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"engine_version":"4.1","league":label,"week":week,
      "scoring":"full PPR" if ppr==1 else "half PPR","league_size":league_size,"my_roster_id":me.get("roster_id") if me else None,
      "waiver_rankings":waiver,"lineup_optimizer":lineup,"trade_targets":trade[:25],
      "model_notes":["Small samples are confidence-discounted.","Opportunity is weighted separately from production.","Depth-chart role and injuries affect scores.","Roster need and positional scarcity are league-specific.","1-QB replacement value suppresses redundant waiver QBs unless the roster needs a starter.","Schedule is neutral until defensive matchup quality is added."]}
def main():
    stats,games=load_nflverse();summary={"generated_at":datetime.now(timezone.utc).isoformat(),"engine_version":"4.1","leagues":{}}
    for label in LEAGUES:
        p=DATA/f"{label}.json"
        if not p.exists():continue
        payload=json.loads(p.read_text());result=league_analysis(label,payload,stats,games)
        out=ANALYSIS/f"{label}_decision_engine.json";out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
        summary["leagues"][label]={"decision_engine":str(out.relative_to(Path(__file__).resolve().parent))}
    (ANALYSIS/"decision_engine_index.json").write_text(json.dumps(summary,indent=2)+"\n")
if __name__=="__main__":main()
