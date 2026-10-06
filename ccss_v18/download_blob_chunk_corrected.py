#!/usr/bin/env python3
import argparse,csv,io,urllib.request
from datetime import date,timedelta
from pathlib import Path
import zstandard as zstd

KEEP=["mmsi","base_date_time","longitude","latitude","sog","cog","heading","vessel_name","imo","call_sign","vessel_type","status","length","width","draft","cargo","transceiver"]
BASE="https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-{date}.csv.zst"

def dates(a,b):
    d=a
    while d<=b:
        yield d
        d+=timedelta(days=1)

def fnum(x):
    try:return float(x)
    except:return None

def fint(x):
    try:return int(float(x))
    except:return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True); ap.add_argument("--end",required=True); ap.add_argument("--out",required=True)
    args=ap.parse_args()
    a=date.fromisoformat(args.start); b=date.fromisoformat(args.end)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    mani=[]
    for d in dates(a,b):
        ds=d.isoformat(); url=BASE.format(date=ds); path=out/f"ais_clip_{ds}.csv"
        n=kept=0
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"CCSS-v18-real-validation/1.0"})
            with urllib.request.urlopen(req,timeout=180) as raw:
                zr=zstd.ZstdDecompressor().stream_reader(raw)
                txt=io.TextIOWrapper(zr,encoding="utf-8-sig",newline="")
                rd=csv.DictReader(txt)
                with path.open("w",newline="",encoding="utf-8") as fo:
                    wr=csv.DictWriter(fo,fieldnames=KEEP,extrasaction="ignore"); wr.writeheader()
                    for row in rd:
                        n+=1
                        lat=fnum(row.get("latitude")); lon=fnum(row.get("longitude"))
                        if lat is None or lon is None or not (29.84<=lat<=29.94 and -90.04<=lon<=-89.94): continue
                        vt=fint(row.get("vessel_type"))
                        if vt not in (31,32,52): continue
                        wr.writerow({k:row.get(k,"") for k in KEEP}); kept+=1
            print(ds,n,kept,flush=True)
            mani.append({"date":ds,"status":"ok","input_rows":n,"retained_rows":kept,"url":url})
        except Exception as e:
            print(ds,"ERROR",repr(e),flush=True)
            mani.append({"date":ds,"status":"error","input_rows":n,"retained_rows":kept,"error":repr(e),"url":url})
    with (out/"manifest.csv").open("w",newline="",encoding="utf-8") as f:
        fields=sorted({k for x in mani for k in x}); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(mani)
if __name__=="__main__":main()
