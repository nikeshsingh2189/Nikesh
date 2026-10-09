# Archive notes

The deterministic core checks, benchmark calculations, ALARM analyses, fixed-DAG pipeline enumeration, pipeline target audit, and complete SMART-DS external structural-validation package are included in this archive.

Raw-data pipeline fitting requires the public Year-1 and Year-7 spreadsheets referenced in `PIPELINE_DATA.md`; those public spreadsheets are not redistributed here.

For SMART-DS, the archive contains all three fixed query sets and all 2,500 relation-level reported cases: 1,000 random valid relations, 1,000 radius-stratified relations, and 500 weighted relations. `external_validation/verify_reported_results.py` recomputes every stored radius/cost independently, while `generate_random_queries.py` regenerates the exact random query set from seed `2026092201`.

Wall-clock runtime values are machine dependent; graph-theoretic radii, weighted costs, query sets, and agreement indicators are deterministic.
