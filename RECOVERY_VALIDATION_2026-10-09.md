# Recovery and validation report — 2026-10-09

Source archive: IISE_Reproducibility_Package_FINAL_CORRECTED.zip, recovered from ChatGPT Library (dated 2026-09-22). This package contains the originally archived computational research code and result inputs, not the provisional reconstructed core provided in the earlier repair ZIP.

Checks executed on the recovered source archive:
- pytest -q tests: 9 passed.
- external_validation/verify_reported_results.py: 2500/2500 exact agreement (1000 random, 1000 stratified, 500 weighted).
- external_validation/generate_random_queries.py: exact query-set match True.
- scripts/audit_reported_numbers.py: 25 passed, 0 failed, 3 skipped.
- run_all.sh through step 6: C++ exhaustive enumeration: 33,866 canonical-order DAGs and 1,950,439 valid queries; 0 unit-cost and weighted mismatches. Random-DAG 2000 cases: 0 unit/weighted mismatches. Chain/clique runs completed, runtimes differed from archived hardware.

Limitations:
- run_all.sh was interrupted at step 7 (benchmarks) by the session execution time limit. This is not a complete fresh-run signoff.
- The three skipped checks require external pipeline Year 1/Year 7 source spreadsheets and fresh pipeline fitting. See PIPELINE_DATA.md.
- Raw pipeline spreadsheets are omitted by design, with public source identified.
- The GitHub repository was not changed. To repair the remote, upload this recovered directory preserving its hierarchy, not individual files into repository root. Do not claim an end-to-end full-run result until run_all.sh finishes on your machine.
