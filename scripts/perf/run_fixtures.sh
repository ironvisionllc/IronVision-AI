#!/bin/bash
# Real v2 benchmark of the three demo/UAT fixtures: scripts/perf/run_fixtures.sh <label-suffix>
cd /app/backend
B="/root/.venv/bin/python /app/scripts/perf/policy_bench.py"
for K in ra ac sc; do
  D=tests/fixtures/policies/${K}_policy_raven_demo.docx; [ $K = ra ] && D=tests/fixtures/policies/ra_policy_dod_aws_raven_demo.docx
  $B ${K}_raven ${K}_v2_$1 --analyzer v2 --fresh-org --with-system --docx $D > /tmp/fx_${K}_$1.log 2>&1
done
touch /tmp/fx_$1.done
