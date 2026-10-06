#!/usr/bin/env python3
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import quote
import io,json,time
import numpy as np, pandas as pd, requests
import run_v18_remote as b

OUT=Path("v18_fast_results"); OUT.mkdir(exist_ok=True)

def fetch_chunk(session,a,z):
    nxt=z+timedelta(days=1)
    fields="MMSI,time,Lat,Lon,SOG,VesselType,VesselName"
    cons=[
      f"time>={a.isoformat()}T00:00:00Z",f"time<{nxt.isoformat()}T00:00:00Z",
      f"Lat>={b.LAT0}",f"Lat<={b.LAT1}",f"Lon>={b.LON0}",f"Lon<={b.LON1}",
      "VesselType>=31","VesselType<=32"]
    url=b.ERDDAP+"?"+quote(fields,safe=",")+"&"+"&".join(quote(x,safe="=><-:.") for x in cons)
    last=None
    for k in range(4):
        try:
            r=session.get(url,timeout=240)
            if r.status_code==404 and "no data" in r.text.lower():
                return pd.DataFrame(),{"start":str(a),"end":str(z),"status":"no_data","rows":0,"url":url}
            r.raise_for_status()
            q=pd.read_csv(io.StringIO(r.text),low_memory=False)
            q["Lat"]=pd.to_numeric(q.get("Lat"),errors="coerce"); q["Lon"]=pd.to_numeric(q.get("Lon"),errors="coerce")
            q["VesselType"]=pd.to_numeric(q.get("VesselType"),errors="coerce"); q["SOG"]=pd.to_numeric(q.get("SOG"),errors="coerce")
            q["time"]=pd.to_datetime(q.get("time"),errors="coerce",utc=True)
            q=q.dropna(subset=["MMSI","time","Lat","Lon"])
            q=q[q["VesselType"].isin(b.VESSEL_TYPES)].copy()
            q["MMSI"]=q["MMSI"].astype(str).str.replace(r"\.0$","",regex=True).str.strip()
            q["timestamp"]=q["time"].dt.tz_convert(None); q["lat"]=q["Lat"]; q["lon"]=q["Lon"]; q["vessel_type"]=q["VesselType"]
            if "VesselName" not in q:q["VesselName"]=""
            q["vessel_name"]=q["VesselName"].fillna("").astype(str)
            keep=["MMSI","timestamp","lat","lon","SOG","vessel_type","vessel_name"]
            q=q[keep].rename(columns={"MMSI":"mmsi","SOG":"sog"})
            return q,{"start":str(a),"end":str(z),"status":"ok","rows":int(len(q)),"url":url}
        except Exception as e:
            last=repr(e); time.sleep(2**k)
    return pd.DataFrame(),{"start":str(a),"end":str(z),"status":"error","rows":0,"error":last,"url":url}

def main():
    s=requests.Session(); s.headers["User-Agent"]="CCSS-v18-research-validation/1.0"
    frames=[]; mani=[]
    a=b.START
    while a<=b.END:
        z=min(a+timedelta(days=6),b.END)
        q,m=fetch_chunk(s,a,z); mani.append(m)
        print(m["start"],m["end"],m["status"],m.get("rows",0),flush=True)
        if len(q): frames.append(q)
        a=z+timedelta(days=1)
    pd.DataFrame(mani).to_csv(OUT/"download_manifest.csv",index=False)
    if not frames: raise RuntimeError("No AIS rows retrieved from ERDDAP.")
    pts=pd.concat(frames,ignore_index=True).drop_duplicates(subset=["mmsi","timestamp","lat","lon"]).sort_values(["mmsi","timestamp"]).reset_index(drop=True)
    pts.to_csv(OUT/"ais_corridor_points.csv",index=False)
    vv=b.visits_for_cp(pts,b.ENTRY)+b.visits_for_cp(pts,b.EXIT)
    visits=pd.DataFrame(vv).sort_values(["mmsi","visit_start","checkpoint_id"]).reset_index(drop=True)
    visits.to_csv(OUT/"checkpoint_visits.csv",index=False)
    tracks=b.pair_visits(visits)
    if tracks.empty: raise RuntimeError("No matched Algiers->Belle Chasse transits found.")
    tracks=tracks[(tracks.entry_points>=2)&(tracks.exit_points>=2)].copy()
    tracks["split"]=tracks.mmsi.map(b.split)
    tracks.to_csv(OUT/"real_route_tracks.csv",index=False)
    cal=tracks[tracks.split=="calibration"]; eva=tracks[tracks.split=="evaluation"]
    if cal.empty or eva.empty: raise RuntimeError(f"Need both splits: cal={len(cal)} eval={len(eva)}")
    mean_h=float(cal.duration_hours.mean()) if len(cal) else b.FALLBACK_MEAN
    grid=pd.date_range(pd.Timestamp("2024-03-14"),pd.Timestamp("2024-05-11 23:59:59"),freq=f"{b.GRID_MIN}min")
    truth=b.truth_series(eva,grid)
    master=np.random.default_rng(b.SEED); rows=[]; ratios=[]; ts=[]
    for rep in range(b.REPS):
        rng=np.random.default_rng(int(master.integers(1_000_000_000)))
        obs=b.masked_obs(tracks,rng); mov,surv,recent=b.estimate_series(obs,grid,mean_h)
        mm=b.metric(truth,mov); ms=b.metric(truth,surv); mr=b.metric(truth,recent)
        rows.append({"replicate":rep,"movement_mae":mm[0],"entry_survival_mae":ms[0],"recent_entry_mae":mr[0],
          "movement_corr":mm[3],"entry_survival_corr":ms[3],"recent_entry_corr":mr[3],
          "gain_vs_entry_survival":ms[0]-mm[0],"gain_vs_recent_entry":mr[0]-mm[0]})
        active=truth>0
        for meth,p in [("movement_informed",mov),("entry_survival",surv),("recent_entry",recent)]:
            rr=np.clip((p[active]+0.5)/(truth[active]+0.5),0.10,3.0)
            ratios.extend({"replicate":rep,"method":meth,"ratio":float(x)} for x in rr)
        if rep<5:ts.append(pd.DataFrame({"time":grid,"true_commitment":truth,"movement":mov,"entry_survival":surv,"recent_entry":recent,"replicate":rep}))
    m=pd.DataFrame(rows); m.to_csv(OUT/"masking_replicate_metrics.csv",index=False)
    pd.DataFrame(ratios).to_csv(OUT/"error_ratio_samples.csv",index=False)
    pd.concat(ts,ignore_index=True).to_csv(OUT/"timeseries_first5.csv",index=False)
    g=m.gain_vs_entry_survival.to_numpy()
    summary={"data_source":"NOAA/PMEL ERDDAP AIS2024_AIS","date_start":str(b.START),"date_end":str(b.END),
      "n_points":int(len(pts)),"unique_towing_mmsi":int(pts.mmsi.nunique()),"n_checkpoint_visits":int(len(visits)),
      "n_matched_tracks":int(len(tracks)),"n_calibration_tracks":int(len(cal)),"n_evaluation_tracks":int(len(eva)),
      "unique_eval_vessels":int(eva.mmsi.nunique()),"calibrated_mean_transit_hours":mean_h,
      "checkpoint_visibility":b.VIS,"record_detection":b.DET,"replicates":b.REPS,
      "movement_mae_mean":float(m.movement_mae.mean()),"entry_survival_mae_mean":float(m.entry_survival_mae.mean()),
      "recent_entry_mae_mean":float(m.recent_entry_mae.mean()),"gain_vs_entry_survival_mean":float(g.mean()),
      "gain_vs_entry_survival_masking_q025":float(np.quantile(g,.025)),"gain_vs_entry_survival_masking_q975":float(np.quantile(g,.975)),
      "movement_corr_mean":float(m.movement_corr.mean()),"entry_survival_corr_mean":float(m.entry_survival_corr.mean()),
      "implementation_note":"Weekly ERDDAP queries; repeated MMSIs segmented into sequential observed episodes; no truth track_id exposed."}
    (OUT/"real_ais_validation_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
