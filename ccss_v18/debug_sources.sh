#!/usr/bin/env bash
set -u
echo "=== PMEL metadata ==="
curl -L -sS -D - --max-time 30 "https://data.pmel.noaa.gov/pmel/erddap/info/AIS2024_AIS/index.csv" | head -80 || true
echo "=== PMEL tiny query ==="
curl -L -sS -D - --max-time 60 "https://data.pmel.noaa.gov/pmel/erddap/tabledap/AIS2024_AIS.csv?MMSI,time,Lat,Lon,SOG,VesselType&time%3E=2024-03-28T00:00:00Z&time%3C2024-03-28T01:00:00Z&Lat%3E=29.84&Lat%3C=29.94&Lon%3E=-90.04&Lon%3C=-89.94" | head -120 || true
echo "=== NOAA blob HEAD ==="
curl -I -L -sS --max-time 30 "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-03-28.csv.zst" || true
echo "=== GeoParquet container list ==="
curl -L -sS --max-time 30 "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre?restype=container&comp=list&prefix=ais2024/&maxresults=20" | head -120 || true
