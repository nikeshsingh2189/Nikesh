#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results

echo "== 1. unit tests"
python3 -m pytest -q tests

echo "== 2. C++ tools"
g++ -O3 -std=c++17 -o cpp/radius_tools cpp/radius_tools.cpp

echo "== 3. exhaustive verification n<=6"
./cpp/radius_tools verify | tee results/exhaustive_verification.txt

echo "== 4. chain scaling"
./cpp/radius_tools chain | tee results/chain_scaling.txt

echo "== 5. high-indegree sparse-graph stress test"
./cpp/radius_tools clique | tee results/clique_stress.txt

echo "== 6. larger random-DAG verification"
python3 scripts/random_dag_check.py | tee results/random_dag_check.txt

echo "== 7. benchmark networks"
python3 scripts/benchmarks.py --n 10000 | tee results/benchmarks_N10000.txt

echo "== 8. ALARM monitoring cases"
python3 scripts/alarm_monitoring_cases.py | tee results/alarm_monitoring_cases.txt

echo "== 9. ALARM protection"
python3 scripts/alarm_protection_design.py | tee results/alarm_protection_design.txt

echo "== 10. ALARM random-loss analysis"
python3 scripts/alarm_random_loss_exact.py | tee results/alarm_random_loss_exact.txt

echo "== 11. fixed-DAG pipeline enumeration"
python3 scripts/pipeline_radius_enumeration.py | tee results/pipeline_radius_enumeration.txt

if [ -n "${YEAR1:-}" ] && [ -n "${YEAR7:-}" ]; then
  echo "== 12. baseline pipeline fitting from public data"
  FULL_ARGS=(--year1 "$YEAR1" --year7 "$YEAR7")
  if [ -n "${YEAR3:-}" ]; then FULL_ARGS+=(--year3 "$YEAR3"); fi
  if [ -n "${YEAR5:-}" ]; then FULL_ARGS+=(--year5 "$YEAR5"); fi
  if [ -n "${YEAR3:-}" ] || [ -n "${YEAR5:-}" ]; then FULL_ARGS+=(--check-epd); fi
  python3 scripts/pipeline_full_bn_run.py "${FULL_ARGS[@]}" | tee results/pipeline_full_bn_run.txt

  echo "== 13. pipeline graph-specification sensitivity and fitted-DAG export"
  python3 scripts/pipeline_sensitivity_run.py --year1 "$YEAR1" --year7 "$YEAR7" --save-dags data | tee results/pipeline_sensitivity_run.txt

  echo "== 14. Figure 6 common-relation sensitivity"
  python3 scripts/pipeline_common_relation_sensitivity.py | tee results/pipeline_common_relation_sensitivity.txt
else
  echo "== 12-14. skipped: set YEAR1 and YEAR7 to the public Mendeley spreadsheets to rerun pipeline fitting/sensitivity"
fi

echo "== 15. archived-number audit"
python3 scripts/audit_reported_numbers.py | tee results/manuscript_number_audit.txt

echo "== 16. SMART-DS stored-result verification"
python3 external_validation/verify_reported_results.py | tee external_validation/verification_current.txt

echo "== 17. SMART-DS random-query regeneration"
python3 external_validation/generate_random_queries.py | tee -a external_validation/verification_current.txt

echo "== 18. SMART-DS complete external validation"
python3 external_validation/run_external_validation_all.py | tee -a external_validation/verification_current.txt

echo "Completed. Outputs are in results/ and external_validation/reproduced_results/."
