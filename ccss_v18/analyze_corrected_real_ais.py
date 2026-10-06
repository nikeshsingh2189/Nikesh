#!/usr/bin/env python3
import glob, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

DATA=Path("ais_clips")
OUT=Path("v18_real_results"); OUT.mkdir(exist_ok=True)
ENTRY=("algiers_lock",29.9151188,-89.972064,0.70)
EXIT=("belle_chasse_mile_3_7",29.871857,-90.008846,0.70)
VISIT_GAP_H=2.0
MIN_TRANSIT_H=0.10
MAX_TRANSIT_H=24.0
SPLIT_SALT="ccss-v18-port-allen-2024"
CAL_FRAC=0.50
WEIB_SHAPE=2.2
PRIMARY_VIS=0.65
PRIMARY_DET=0.85
N_MASK=200
SEED=20241005
GRID_FREQ="30min"
CLOSURE_START=pd.Timestamp("2024-03-28 00:00:00")
CLOSURE_END=pd.Timestamp("2024-04-27 23:59:59")
WINDOW_START=pd.Timestamp("2024-03-14 00:00:00")
WINDOW_END=pd.Timestamp("2024-05-11 23:59:59")

def hav(lat,lon,clat,clon):
    r=6371.0088
    a1=np.radians(lat); a2=math.radians(clat)
    da=a2-a1; db=np.radians(clon-lon)
    aa=np.sin(da/2)**2+np.cos(a1)*math.cos(a2)*np.sin(db/2)**2
    return 2*r*np.arcsin(np.sqrt(np.clip(aa,0,1)))

def load_points():
    files=sorted([p for p in DATA.rglob("ais_clip_*.csv")])
    frames=[]
    for p in files:
        try:
            z=pd.read_csv(p,low_memory=False)
        except Exception:
            continue
        if len(z)==0: continue
        z.columns=[str(c).strip().lower() for c in z.columns]
        ren={}
        if "basedatetime" in z: ren["basedatetime"]="base_date_time"
        if "lat" in z: ren["lat"]="latitude"
        if "lon" in z: ren["lon"]="longitude"
        if "vesseltype" in z: ren["vesseltype"]="vessel_type"
        if "vesselname" in z: ren["vesselname"]="vessel_name"
        if "mmsi" not in z: continue
        z=z.rename(columns=ren)
        need=["mmsi","base_date_time","latitude","longitude","vessel_type"]
        if any(c not in z for c in need): continue
        z["time"]=pd.to_datetime(z["base_date_time"],errors="coerce",utc=True).dt.tz_convert(None)
        for c in ["latitude","longitude","vessel_type"]:
            z[c]=pd.to_numeric(z[c],errors="coerce")
        z=z.dropna(subset=["mmsi","time","latitude","longitude"])
        z["mmsi"]=z["mmsi"].astype(str).str.replace(r"\.0$","",regex=True).str.strip()
        if "vessel_name" not in z: z["vessel_name"]=""
        z["vessel_name"]=z["vessel_name"].fillna("").astype(str)
        frames.append(z[["mmsi","time","latitude","longitude","vessel_type","vessel_name"]])
    if not frames: raise RuntimeError("No corrected AIS clip rows found.")
    pts=pd.concat(frames,ignore_index=True)
    pts=pts.drop_duplicates(subset=["mmsi","time","latitude","longitude"]).sort_values(["mmsi","time"]).reset_index(drop=True)
    return pts

def visits(points,cp):
    cid,clat,clon,rad=cp
    q=points.copy()
    q["distance_km"]=hav(q.latitude.to_numpy(),q.longitude.to_numpy(),clat,clon)
    q=q[q.distance_km<=rad].copy()
    out=[]
    gap=pd.Timedelta(hours=VISIT_GAP_H)
    for m,g in q.groupby("mmsi",sort=False):
        g=g.sort_values("time")
        cur=[]; prev=None
        for r in g.itertuples(index=False):
            if prev is None or r.time-prev<=gap:
                cur.append(r)
            else:
                out.append(pack_visit(str(m),cid,cur)); cur=[r]
            prev=r.time
        if cur: out.append(pack_visit(str(m),cid,cur))
    return pd.DataFrame(out)

def pack_visit(m,cid,rr):
    return {
      "mmsi":m,"checkpoint":cid,
      "visit_start":min(x.time for x in rr),"visit_end":max(x.time for x in rr),
      "n_points":len(rr),"min_distance_km":float(min(x.distance_km for x in rr)),
      "vessel_type":float(next((x.vessel_type for x in rr if pd.notna(x.vessel_type)),np.nan)),
      "vessel_name":next((str(x.vessel_name) for x in rr if str(x.vessel_name)), "")
    }

def build_tracks(vis):
    rows=[]
    for m,g in vis.groupby("mmsi",sort=False):
        g=g.sort_values(["visit_start","checkpoint"]).reset_index(drop=True)
        seq=[]
        for r in g.itertuples(index=False):
            if seq and seq[-1]["checkpoint"]==r.checkpoint:
                seq[-1]["visit_end"]=max(seq[-1]["visit_end"],r.visit_end)
                seq[-1]["n_points"]+=int(r.n_points)
                seq[-1]["min_distance_km"]=min(seq[-1]["min_distance_km"],float(r.min_distance_km))
            else:
                seq.append({"checkpoint":r.checkpoint,"visit_start":r.visit_start,"visit_end":r.visit_end,
                            "n_points":int(r.n_points),"min_distance_km":float(r.min_distance_km),
                            "vessel_type":r.vessel_type,"vessel_name":r.vessel_name})
        k=0
        for a,b in zip(seq[:-1],seq[1:]):
            if a["checkpoint"]==b["checkpoint"]: continue
            dur=(b["visit_start"]-a["visit_start"]).total_seconds()/3600
            if not (MIN_TRANSIT_H<=dur<=MAX_TRANSIT_H): continue
            if a["n_points"]<2 or b["n_points"]<2: continue
            k+=1
            rows.append({"track_id":f"{m}:{k}","mmsi":m,
                "direction":f"{a['checkpoint']}_to_{b['checkpoint']}",
                "entry_checkpoint":a["checkpoint"],"exit_checkpoint":b["checkpoint"],
                "entry_time":a["visit_start"],"entry_end":a["visit_end"],
                "completion_time":b["visit_start"],"duration_hours":dur,
                "entry_points":a["n_points"],"exit_points":b["n_points"],
                "vessel_type":a["vessel_type"],"vessel_name":a["vessel_name"]})
    return pd.DataFrame(rows)

def split_mmsi(m):
    h=hashlib.sha256((SPLIT_SALT+":"+str(m)).encode()).digest()
    u=int.from_bytes(h[:8],"big")/(2**64-1)
    return "calibration" if u<CAL_FRAC else "evaluation"

def weib_surv(age,mean):
    if age<=0:return 1.0
    scale=max(mean,1e-9)/math.gamma(1+1/WEIB_SHAPE)
    return math.exp(-((age/scale)**WEIB_SHAPE))

def means_by_direction(cal):
    out={}
    for d,g in cal.groupby("direction"):
        out[d]=float(g.duration_hours.mean())
    return out

def truth_series(tracks,grid):
    if tracks.empty:return np.zeros(len(grid))
    a=tracks.entry_time.to_numpy(dtype="datetime64[ns]")
    b=tracks.completion_time.to_numpy(dtype="datetime64[ns]")
    return np.asarray([np.sum((a<=np.datetime64(t))&(b>np.datetime64(t))) for t in grid],float)

def masked_episodes(eval_tracks,rng,pvis,pdet):
    rows=[]
    for r in eval_tracks.itertuples(index=False):
        if rng.random()<=pdet:
            rows.append({"track_id":r.track_id,"mmsi":r.mmsi,"direction":r.direction,
                         "entry_time":r.entry_time,"completion_time":r.completion_time if (rng.random()<=pvis*pdet) else pd.NaT})
    return pd.DataFrame(rows)

def estimates(masked,grid,means,pdet):
    mov=np.zeros(len(grid)); surv=np.zeros(len(grid)); recent=np.zeros(len(grid))
    if masked.empty:return mov,surv,recent
    for r in masked.itertuples(index=False):
        mu=float(means.get(r.direction,np.nan))
        if not np.isfinite(mu): continue
        w=1.0/max(pdet,1e-9)
        for i,t in enumerate(grid):
            if t<r.entry_time: continue
            age=(t-r.entry_time).total_seconds()/3600
            surv[i]+=w*weib_surv(age,mu)
            if age<=mu: recent[i]+=w
            if pd.notna(r.completion_time):
                if t<r.completion_time: mov[i]+=w
            else:
                mov[i]+=w*weib_surv(age,mu)
    return mov,surv,recent

def metric(y,p):
    e=p-y
    corr=float(np.corrcoef(p,y)[0,1]) if np.std(p)>0 and np.std(y)>0 else np.nan
    return {"mae":float(np.mean(np.abs(e))),"rmse":float(np.sqrt(np.mean(e*e))),"bias":float(np.mean(e)),"corr":corr}

def run_masking(eval_tracks,means,label,pvis,pdet,grid,truth,n=N_MASK):
    rng0=np.random.default_rng(SEED+sum(ord(c) for c in label))
    rows=[]
    for rep in range(n):
        rng=np.random.default_rng(int(rng0.integers(1_000_000_000)))
        masked=masked_episodes(eval_tracks,rng,pvis,pdet)
        mov,surv,recent=estimates(masked,grid,means,pdet)
        mm=metric(truth,mov); ms=metric(truth,surv); mr=metric(truth,recent)
        rows.append({"calibration":label,"replicate":rep,"p_visibility":pvis,"p_detection":pdet,
                     "movement_mae":mm["mae"],"entry_survival_mae":ms["mae"],"recent_entry_mae":mr["mae"],
                     "movement_corr":mm["corr"],"entry_survival_corr":ms["corr"],"recent_entry_corr":mr["corr"],
                     "gain_vs_entry_survival":ms["mae"]-mm["mae"],"gain_vs_recent_entry":mr["mae"]-mm["mae"]})
    return pd.DataFrame(rows)

def main():
    pts=load_points()
    va=visits(pts,ENTRY); vb=visits(pts,EXIT)
    vis=pd.concat([va,vb],ignore_index=True).sort_values(["mmsi","visit_start","checkpoint"]).reset_index(drop=True)
    tracks=build_tracks(vis)
    if tracks.empty: raise RuntimeError("No matched checkpoint transits found.")
    tracks["split"]=tracks.mmsi.map(split_mmsi)
    tracks["period"]=np.where(tracks.entry_time<CLOSURE_START,"pre",
                     np.where(tracks.entry_time<=CLOSURE_END,"closure","post"))
    cal=tracks[tracks.split=="calibration"].copy()
    eva=tracks[tracks.split=="evaluation"].copy()
    eva_closure=eva[(eva.entry_time>=CLOSURE_START)&(eva.entry_time<=CLOSURE_END)].copy()
    if cal.empty or eva_closure.empty: raise RuntimeError(f"Insufficient split: cal={len(cal)} eval_closure={len(eva_closure)}")

    means_all=means_by_direction(cal)
    cal_pre=cal[cal.entry_time<CLOSURE_START]
    means_pre=means_by_direction(cal_pre)
    # Fall back direction-by-direction to all-calibration mean only if a pre-period direction has no sample.
    for d,v in means_all.items(): means_pre.setdefault(d,v)

    grid=pd.date_range(CLOSURE_START,CLOSURE_END,freq=GRID_FREQ)
    truth=truth_series(eva_closure,grid)
    primary_all=run_masking(eva_closure,means_all,"vessel_holdout_allwindow",PRIMARY_VIS,PRIMARY_DET,grid,truth)
    primary_pre=run_masking(eva_closure,means_pre,"preclosure_calibration",PRIMARY_VIS,PRIMARY_DET,grid,truth)
    full=run_masking(eva_closure,means_pre,"preclosure_calibration_fullobs",1.0,1.0,grid,truth,n=1)
    results=pd.concat([primary_all,primary_pre,full],ignore_index=True)
    results.to_csv(OUT/"masking_results.csv",index=False)

    def summarise(g):
        x=g.gain_vs_entry_survival.to_numpy()
        return pd.Series({
          "movement_mae_mean":g.movement_mae.mean(),
          "entry_survival_mae_mean":g.entry_survival_mae.mean(),
          "recent_entry_mae_mean":g.recent_entry_mae.mean(),
          "gain_vs_entry_survival_mean":x.mean(),
          "gain_masking_q025":np.quantile(x,.025),
          "gain_masking_q975":np.quantile(x,.975),
          "movement_corr_mean":g.movement_corr.mean(),
          "entry_survival_corr_mean":g.entry_survival_corr.mean()
        })
    summary=results.groupby(["calibration","p_visibility","p_detection"],dropna=False).apply(summarise,include_groups=False).reset_index()
    summary.to_csv(OUT/"masking_summary.csv",index=False)

    daily=tracks.assign(day=tracks.entry_time.dt.floor("D")).groupby(["day","period","direction"]).size().rename("transits").reset_index()
    daily.to_csv(OUT/"real_daily_transits.csv",index=False)
    period=tracks.groupby(["period","direction"]).agg(n_transits=("track_id","count"),unique_vessels=("mmsi","nunique"),
                    mean_duration_h=("duration_hours","mean"),median_duration_h=("duration_hours","median")).reset_index()
    period.to_csv(OUT/"real_period_summary.csv",index=False)

    vis.to_csv(OUT/"checkpoint_visits.csv",index=False)
    tracks.to_csv(OUT/"real_route_tracks.csv",index=False)

    audit={
      "source":"NOAA 2024 AIS daily .csv.zst files; corrected lowercase raw fields",
      "n_ais_points":int(len(pts)),"unique_towlike_mmsi":int(pts.mmsi.nunique()),
      "n_entry_visits":int(len(va)),"n_exit_visits":int(len(vb)),"n_matched_transits":int(len(tracks)),
      "n_calibration_transits":int(len(cal)),"n_eval_closure_transits":int(len(eva_closure)),
      "unique_eval_closure_vessels":int(eva_closure.mmsi.nunique()),
      "means_allwindow_h":means_all,"means_preclosure_h":means_pre,
      "primary_visibility":PRIMARY_VIS,"primary_detection":PRIMARY_DET,
      "primary_result_preclosure_calibration":summary[summary.calibration=="preclosure_calibration"].to_dict(orient="records"),
      "full_observation_result":summary[summary.calibration=="preclosure_calibration_fullobs"].to_dict(orient="records"),
      "interpretation_boundary":"This is real-trajectory controlled-missingness validation. Full NOAA AIS defines observed route episodes; missingness is imposed synthetically. It is not validation against an independent ground-truth commitment registry."
    }
    (OUT/"V18_REAL_AIS_SUMMARY.json").write_text(json.dumps(audit,indent=2,default=str))
    print(json.dumps(audit,indent=2,default=str))

if __name__=="__main__": main()
