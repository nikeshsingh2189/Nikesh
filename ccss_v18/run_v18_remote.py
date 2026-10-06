#!/usr/bin/env python3
import csv, hashlib, io, json, math, os, time
from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd
import requests

ERDDAP = "https://data.pmel.noaa.gov/pmel/erddap/tabledap/AIS2024_AIS.csv"
START = date(2024,3,14)
END = date(2024,5,11)
LAT0,LON0,LAT1,LON1 = 29.84,-90.04,29.94,-89.94
VESSEL_TYPES={31,32}
ENTRY=("algiers_lock",29.9151188,-89.972064,0.7)
EXIT=("belle_chasse_mile_3_7",29.871857,-90.008846,0.7)
MIN_H,MAX_H=0.25,12.0
COOLDOWN_H=1.0
CAL_FRAC=0.5
SALT="ccss-v18-port-allen-2024"
TAIL_SHAPE=2.2
FALLBACK_MEAN=4.0
VIS=0.65
DET=0.85
REPS=100
SEED=20241005
GRID_MIN=30
OUT=Path("v18_results"); OUT.mkdir(exist_ok=True)

def daterange(a,b):
    d=a
    while d<=b:
        yield d
        d += timedelta(days=1)

def erddap_url(d):
    n=d+timedelta(days=1)
    fields="MMSI,time,Lat,Lon,SOG,VesselType,VesselName"
    constraints=[
      f"time>={d.isoformat()}T00:00:00Z",f"time<{n.isoformat()}T00:00:00Z",
      f"Lat>={LAT0}",f"Lat<={LAT1}",f"Lon>={LON0}",f"Lon<={LON1}",
      "VesselType>=31","VesselType<=32"]
    from urllib.parse import quote
    return ERDDAP+"?"+quote(fields,safe=",")+"&"+"&".join(quote(x,safe="=><-:.") for x in constraints)

def fetch_day(session,d):
    url=erddap_url(d)
    last=None
    for k in range(5):
        try:
            r=session.get(url,timeout=120)
            if r.status_code==404 and ("no data" in r.text.lower() or "there is no data" in r.text.lower()):
                return pd.DataFrame(), {"date":str(d),"status":"no_data","rows":0,"url":url}
            r.raise_for_status()
            z=pd.read_csv(io.StringIO(r.text),low_memory=False)
            # ERDDAP .csv may include a units row; coercion below removes it.
            z["Lat"]=pd.to_numeric(z.get("Lat"),errors="coerce")
            z["Lon"]=pd.to_numeric(z.get("Lon"),errors="coerce")
            z["VesselType"]=pd.to_numeric(z.get("VesselType"),errors="coerce")
            z["SOG"]=pd.to_numeric(z.get("SOG"),errors="coerce")
            z["time"]=pd.to_datetime(z.get("time"),errors="coerce",utc=True)
            z=z.dropna(subset=["MMSI","time","Lat","Lon"])
            z=z[z["VesselType"].isin(VESSEL_TYPES)].copy()
            z["MMSI"]=z["MMSI"].astype(str).str.replace(r"\.0$","",regex=True).str.strip()
            z["timestamp"]=z["time"].dt.tz_convert(None)
            z["lat"]=z["Lat"]; z["lon"]=z["Lon"]; z["vessel_type"]=z["VesselType"]
            if "VesselName" not in z: z["VesselName"]=""
            z["vessel_name"]=z["VesselName"].fillna("").astype(str)
            keep=["MMSI","timestamp","lat","lon","SOG","vessel_type","vessel_name"]
            return z[keep].rename(columns={"MMSI":"mmsi","SOG":"sog"}), {"date":str(d),"status":"ok","rows":int(len(z)),"url":url}
        except Exception as e:
            last=repr(e)
            time.sleep(2**k)
    return pd.DataFrame(), {"date":str(d),"status":"error","rows":0,"error":last,"url":url}

def hav(lat1,lon1,lat2,lon2):
    r=6371.0088
    a1=np.radians(lat1); b1=np.radians(lon1); a2=np.radians(lat2); b2=np.radians(lon2)
    da=a2-a1; db=b2-b1
    aa=np.sin(da/2)**2+np.cos(a1)*np.cos(a2)*np.sin(db/2)**2
    return 2*r*np.arcsin(np.sqrt(np.clip(aa,0,1)))

def visits_for_cp(points,cp):
    cid,clat,clon,rad=cp
    if points.empty: return []
    q=points.copy()
    q["dist"]=hav(q.lat.to_numpy(),q.lon.to_numpy(),clat,clon)
    q=q[q.dist<=rad].copy()
    out=[]; cd=pd.Timedelta(hours=COOLDOWN_H)
    for m,g in q.groupby("mmsi",sort=False):
        g=g.sort_values("timestamp"); cur=[]; prev=None
        for row in g.itertuples(index=False):
            if prev is None or row.timestamp-prev<=cd: cur.append(row)
            else:
                out.append(pack_visit(m,cid,cur)); cur=[row]
            prev=row.timestamp
        if cur: out.append(pack_visit(m,cid,cur))
    return out

def pack_visit(m,cid,rr):
    return {"mmsi":str(m),"vessel_name":next((str(x.vessel_name) for x in rr if str(x.vessel_name)), ""),
            "vessel_type":next((x.vessel_type for x in rr if pd.notna(x.vessel_type)),np.nan),
            "checkpoint_id":cid,"visit_start":min(x.timestamp for x in rr),"visit_end":max(x.timestamp for x in rr),
            "n_points":len(rr),"min_distance_km":float(min(x.dist for x in rr))}

def pair_visits(v):
    rows=[]
    for m,g in v.groupby("mmsi",sort=False):
        ent=g[g.checkpoint_id==ENTRY[0]].sort_values("visit_start")
        ex=g[g.checkpoint_id==EXIT[0]].sort_values("visit_start")
        used=set(); k=0
        for e in ent.itertuples(index=False):
            best=None; bi=None
            for idx,x in ex.iterrows():
                if idx in used: continue
                dt=(pd.Timestamp(x.visit_start)-pd.Timestamp(e.visit_start)).total_seconds()/3600
                if dt<MIN_H: continue
                if dt>MAX_H: break
                best=x; bi=idx; break
            if best is None: continue
            used.add(bi); k+=1
            comp=pd.Timestamp(best.visit_start)
            rows.append({"route_key":"algiers_alternate_lock_to_mile_3_7","track_id":f"r:{m}:{k}",
              "mmsi":str(m),"vessel_name":e.vessel_name,"vessel_type":e.vessel_type,
              "entry_time":pd.Timestamp(e.visit_start),"entry_end":pd.Timestamp(e.visit_end),
              "completion_time":comp,"duration_hours":(comp-pd.Timestamp(e.visit_start)).total_seconds()/3600,
              "matched_completion":True,"entry_points":int(e.n_points),"exit_points":int(best.n_points)})
    return pd.DataFrame(rows)

def split(m):
    h=hashlib.sha256((SALT+":"+str(m)).encode()).digest()
    u=int.from_bytes(h[:8],"big")/float(2**64-1)
    return "calibration" if u<CAL_FRAC else "evaluation"

def weib_surv(age,mean,shape):
    if age<=0:return 1.0
    scale=max(mean,1e-6)/math.gamma(1+1/max(shape,1e-6))
    return math.exp(-((age/scale)**shape))

# Repeated-transit-safe observational reconstruction:
# entries and exits are paired sequentially within MMSI after masking, so no truth track_id is used.
def masked_obs(tracks,rng):
    rows=[]
    for r in tracks[tracks["split"]=="evaluation"].itertuples(index=False):
        if rng.random()<=DET:
            rows.append({"mmsi":r.mmsi,"kind":"entry","time":r.entry_time,"exit_of_entry":r.entry_end})
        if rng.random()<=VIS and rng.random()<=DET:
            rows.append({"mmsi":r.mmsi,"kind":"exit","time":r.completion_time,"exit_of_entry":pd.NaT})
    return pd.DataFrame(rows)

def infer_episodes(obs):
    if obs.empty:return []
    eps=[]
    for m,g in obs.groupby("mmsi",sort=False):
        g=g.sort_values("time")
        pending=[]
        for r in g.itertuples(index=False):
            if r.kind=="entry":
                pending.append({"mmsi":m,"entry":pd.Timestamp(r.time),"entry_end":pd.Timestamp(r.exit_of_entry),"completion":pd.NaT})
            elif r.kind=="exit":
                # close oldest feasible pending entry
                x=pd.Timestamp(r.time); pick=None
                for j,p in enumerate(pending):
                    dt=(x-p["entry"]).total_seconds()/3600
                    if MIN_H<=dt<=MAX_H and pd.isna(p["completion"]):
                        pick=j; break
                if pick is not None:
                    pending[pick]["completion"]=x
                    eps.append(pending.pop(pick))
        eps.extend(pending)
    return eps

def truth_series(eval_tracks,grid):
    a=eval_tracks.entry_time.to_numpy(dtype="datetime64[ns]")
    b=eval_tracks.completion_time.to_numpy(dtype="datetime64[ns]")
    vals=[]
    for t in grid:
        tt=np.datetime64(pd.Timestamp(t))
        vals.append(int(np.sum((a<=tt)&(b>tt))))
    return np.asarray(vals,float)

def estimate_series(obs,grid,mean_h):
    eps=infer_episodes(obs)
    move=np.zeros(len(grid)); surv=np.zeros(len(grid)); recent=np.zeros(len(grid))
    entries=obs[obs.kind=="entry"] if not obs.empty else pd.DataFrame()
    for i,t in enumerate(grid):
        t=pd.Timestamp(t)
        for p in eps:
            if t<p["entry"]: continue
            w=1/max(DET,1e-9)
            if pd.notna(p["completion"]):
                if t<p["completion"]: move[i]+=w
            elif t<=p["entry_end"]: move[i]+=w
            else: move[i]+=w*weib_surv((t-p["entry_end"]).total_seconds()/3600,mean_h,TAIL_SHAPE)
        if not entries.empty:
            for r in entries.itertuples(index=False):
                if t<r.time: continue
                age=(t-pd.Timestamp(r.time)).total_seconds()/3600
                surv[i]+=weib_surv(age,mean_h,TAIL_SHAPE)/max(DET,1e-9)
                if age<=mean_h: recent[i]+=1/max(DET,1e-9)
    return move,surv,recent

def metric(y,p):
    e=p-y
    corr=float(np.corrcoef(p,y)[0,1]) if np.std(p)>0 and np.std(y)>0 else np.nan
    return float(np.mean(np.abs(e))),float(np.sqrt(np.mean(e*e))),float(np.mean(e)),corr

def main():
    s=requests.Session(); s.headers["User-Agent"]="CCSS-v18-research-validation/1.0"
    frames=[]; manifest=[]
    for d in daterange(START,END):
        z,meta=fetch_day(s,d); manifest.append(meta)
        print(meta["date"],meta["status"],meta.get("rows",0),flush=True)
        if len(z): frames.append(z)
    pd.DataFrame(manifest).to_csv(OUT/"download_manifest.csv",index=False)
    if not frames: raise RuntimeError("No AIS rows retrieved from ERDDAP.")
    pts=pd.concat(frames,ignore_index=True).sort_values(["mmsi","timestamp"]).reset_index(drop=True)
    pts.to_csv(OUT/"ais_corridor_points.csv",index=False)
    vv=visits_for_cp(pts,ENTRY)+visits_for_cp(pts,EXIT)
    visits=pd.DataFrame(vv).sort_values(["mmsi","visit_start","checkpoint_id"]).reset_index(drop=True)
    visits.to_csv(OUT/"checkpoint_visits.csv",index=False)
    tracks=pair_visits(visits)
    if tracks.empty: raise RuntimeError("No matched Algiers->Belle Chasse transits found.")
    tracks=tracks[(tracks.entry_points>=2)&(tracks.exit_points>=2)].copy()
    tracks["split"]=tracks.mmsi.map(split)
    tracks.to_csv(OUT/"real_route_tracks.csv",index=False)
    cal=tracks[tracks.split=="calibration"]; eva=tracks[tracks.split=="evaluation"]
    if cal.empty or eva.empty: raise RuntimeError(f"Need both splits: cal={len(cal)} eval={len(eva)}")
    mean_h=float(cal.duration_hours.mean()) if len(cal) else FALLBACK_MEAN
    grid=pd.date_range(pd.Timestamp("2024-03-14"),pd.Timestamp("2024-05-11 23:59:59"),freq=f"{GRID_MIN}min")
    truth=truth_series(eva,grid)
    master=np.random.default_rng(SEED)
    rows=[]; ratios=[]; ts=[]
    for rep in range(REPS):
        rng=np.random.default_rng(int(master.integers(1_000_000_000)))
        obs=masked_obs(tracks,rng)
        mov,surv,recent=estimate_series(obs,grid,mean_h)
        mm=metric(truth,mov); ms=metric(truth,surv); mr=metric(truth,recent)
        rows.append({"replicate":rep,"movement_mae":mm[0],"entry_survival_mae":ms[0],"recent_entry_mae":mr[0],
          "movement_corr":mm[3],"entry_survival_corr":ms[3],"recent_entry_corr":mr[3],
          "gain_vs_entry_survival":ms[0]-mm[0],"gain_vs_recent_entry":mr[0]-mm[0]})
        active=truth>0
        for meth,p in [("movement_informed",mov),("entry_survival",surv),("recent_entry",recent)]:
            rr=np.clip((p[active]+0.5)/(truth[active]+0.5),0.10,3.0)
            ratios.extend({"replicate":rep,"method":meth,"ratio":float(x)} for x in rr)
        if rep<5:
            ts.append(pd.DataFrame({"time":grid,"true_commitment":truth,"movement":mov,"entry_survival":surv,"recent_entry":recent,"replicate":rep}))
    m=pd.DataFrame(rows); m.to_csv(OUT/"masking_replicate_metrics.csv",index=False)
    pd.DataFrame(ratios).to_csv(OUT/"error_ratio_samples.csv",index=False)
    pd.concat(ts,ignore_index=True).to_csv(OUT/"timeseries_first5.csv",index=False)
    g=m.gain_vs_entry_survival.to_numpy()
    summary={
      "data_source":"NOAA/PMEL ERDDAP AIS2024_AIS",
      "date_start":str(START),"date_end":str(END),"bbox":[LAT0,LON0,LAT1,LON1],
      "n_points":int(len(pts)),"unique_towing_mmsi":int(pts.mmsi.nunique()),"n_checkpoint_visits":int(len(visits)),
      "n_matched_tracks":int(len(tracks)),"n_calibration_tracks":int(len(cal)),"n_evaluation_tracks":int(len(eva)),
      "unique_eval_vessels":int(eva.mmsi.nunique()),"calibrated_mean_transit_hours":mean_h,
      "checkpoint_visibility":VIS,"record_detection":DET,"replicates":REPS,
      "movement_mae_mean":float(m.movement_mae.mean()),"entry_survival_mae_mean":float(m.entry_survival_mae.mean()),
      "recent_entry_mae_mean":float(m.recent_entry_mae.mean()),"gain_vs_entry_survival_mean":float(g.mean()),
      "gain_vs_entry_survival_masking_q025":float(np.quantile(g,.025)),"gain_vs_entry_survival_masking_q975":float(np.quantile(g,.975)),
      "movement_corr_mean":float(m.movement_corr.mean()),"entry_survival_corr_mean":float(m.entry_survival_corr.mean()),
      "implementation_note":"Repeated MMSIs are segmented into sequential observed entry/exit episodes after masking; no truth track_id is exposed to reconstruction."
    }
    (OUT/"real_ais_validation_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=="__main__":
    main()
