# Pipeline turnover-scale sensitivity

This folder reproduces the turnover-scale sensitivity check for the repeated pipeline-inspection application.

The manuscript uses Q_it <= gamma s_it, with primary scale s_it = max(1, C_i,t-1). The sensitivity check considers 0.5 times and 2 times the primary scale. Because the constraint is linear in the scale, the implied admissible integer turnover is unchanged and gamma rescales inversely.

The script uses the reported primary thresholds and reproduces this additional scale-sensitivity calculation exactly. It does not reproduce the original LP/MILP solver calculation.

Run with Python 3.9+ and no external packages:

    python turnover_scale_sensitivity.py

Primary reported relaxed thresholds: R=40,60,80,100 -> 0.0000, 0.0067, 0.0052, 0.0062.
Primary reported exact integer thresholds: R=40,60,80,100 -> 0.0000, 0.0182, 0.0149, 0.0161.

For scale multiplier a, gamma_new = gamma_primary / a. Thus 0.5 times the scale doubles gamma and 2 times the scale halves gamma. The implied admissible integer turnover is unchanged.

The generated CSV is intended as a reproducibility supplement for the manuscript's turnover-scale sensitivity analysis.
