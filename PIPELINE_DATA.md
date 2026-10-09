# Public pipeline data required for raw-data fitting

The raw-data fitting scripts use the public Mendeley Data release associated with the pipeline application:

The raw-data fitting scripts in this archive implement the workflow documented in Supplementary Material D.

- DOI: `10.17632/c2h2jf5c54.1`
- `External Feature Year One.xlsx`
- `External Feature Year Seven.xlsx`

The release also contains Years 3 and 5, but the descriptive DAG is fit independently to Years 1 and 7 because `SO.deg` is available in those two inspection runs.

Required source fields are `JL.m`, `RD.m`, `SO.deg`, `SPD.m`, `SPO.deg`, `EPD.m`, `SIPRD.m`, `SIPO.deg`, `L.mm`, `W.mm`, and `MD.mm`.

The nine analysis nodes are constructed as follows.

- `SO = SO.deg`
- `UR = RD.m / JL.m`
- `SPO = SPO.deg`
- `L = L.mm`
- `W = W.mm`
- `UE = (EPD.m - SPD.m + RD.m) / JL.m`
- `US = SIPRD.m / JL.m`
- `SIPO = SIPO.deg`
- `MD = MD.mm`

Continuous nodes use pooled Year-1/Year-7 quantile cut points. `SO`, `SPO`, and `SIPO` use eight 45-degree sectors. The prespecified order is `SO, UR, SPO, L, W, UE, US, SIPO, MD`. Each node chooses its parent set from earlier nodes by local discrete BIC, with complete-case scoring for each candidate family.

Run the baseline fit with

```bash
python scripts/pipeline_full_bn_run.py \
  --year1 "/path/External Feature Year One.xlsx" \
  --year7 "/path/External Feature Year Seven.xlsx"
```

Run all discretization/parent-cap scenarios and export the validated quartile fitted graphs with

```bash
python scripts/pipeline_sensitivity_run.py \
  --year1 "/path/External Feature Year One.xlsx" \
  --year7 "/path/External Feature Year Seven.xlsx" \
  --save-dags data
```

Then reproduce the common-556 relation analysis with

```bash
python scripts/pipeline_common_relation_sensitivity.py
```

For every sensitivity scenario, the DAG is prespecified as the common Year-1/Year-7 fit when the two fits are identical and otherwise as their edge intersection. Published values are used only after the graph is constructed as validation checks. The sensitivity workflow validates the published scenario counts and the common-set result: 556 relations valid under all three quartile parent-cap specifications, of which 120 break after SO loss under all three, 134 break under some, and 302 survive under all three. Within the partial group, 64 break only under cap 3 and 70 break under caps 2 and 3. The cap-1 and cap-3 edge lists are generated from the public files and are not replaced by manuscript target values.
