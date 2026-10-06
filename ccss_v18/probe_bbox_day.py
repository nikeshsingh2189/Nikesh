#!/usr/bin/env python3
import csv,io,urllib.request,collections,json
import zstandard as zstd
URL="https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-03-28.csv.zst"
rows=[]; counts=collections.Counter()
req=urllib.request.Request(URL,headers={"User-Agent":"CCSS-v18-probe/1.0"})
with urllib.request.urlopen(req,timeout=180) as raw:
    zr=zstd.ZstdDecompressor().stream_reader(raw)
    txt=io.TextIOWrapper(zr,encoding="utf-8-sig",newline="")
    rd=csv.DictReader(txt)
    print("FIELDS",rd.fieldnames,flush=True)
    for r in rd:
        try: lat=float(r.get("LAT","")); lon=float(r.get("LON",""))
        except: continue
        if 29.84<=lat<=29.94 and -90.04<=lon<=-89.94:
            counts[str(r.get("VesselType",""))]+=1
            if len(rows)<5000: rows.append(r)
print("TYPE_COUNTS",json.dumps(counts.most_common(40)),flush=True)
fields=rd.fieldnames
with open("bbox_probe.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
with open("type_counts.json","w") as f: json.dump(dict(counts),f,indent=2)
