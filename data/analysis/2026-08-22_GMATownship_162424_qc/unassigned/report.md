# QC report — run `unassigned` (static)

- Session dir: `data/ranging_experiments/2026-08-22_GMATownship_session02/raw/20260822_162424-Initiator`
- Generated: 2026-09-10 23:36 UTC by qc_session.py v1.0.0 (raw CSVs read-only, unmodified)
- Expected config: 2400.0 MHz, BW 406.25 kHz, SF8, CR 4/7, 12 dBm; N=100/file; cadence 686.0 ms ±5%; drift limit 15.0 m; warm-up window 5.0 s
- Ground truth: session plan `session_plan.json` (operator-supplied; used only where CSV line-2 TRUE_DISTANCE_M is absent)

## Verdict: **PASS**

No machine-checkable Methodology §11 discard trigger found in this run.

> The following Methodology §11 discard criteria are **not machine-checkable from CSVs** and must be confirmed against the session log: (a) cone moved mid-session without re-measurement; (b) material weather change mid-session (rain start, wind category shift). This tool checks only: firmware reboot / power-loss evidence (short or truncated files), and the >10-consecutive-ERROR abort criterion.

## 1. Manifest integrity

| file | manifest expected | manifest actual | on-disk | status | ok |
|---|---|---|---|---|---|
| `pucklog_D4DB1C_16.csv` | 236 | 236 | 236 | OK | ✓ |
| `pucklog_D4DB1C_17.csv` | 236 | 236 | 236 | OK | ✓ |

## 2. Per-file checks

| file | truth (src) | N | vs spec | cadence ms | S / T / E (rate) | max ERR streak | drift m | flags |
|---|---|---|---|---|---|---|---|---|
| `pucklog_D4DB1C_16.csv` | — | 0 | -100 | — | 0 (0%) / 0 (0%) / 0 (0%) | 0 | — | 2 |
| `pucklog_D4DB1C_17.csv` | — | 0 | -100 | — | 0 (0%) / 0 (0%) / 0 (0%) | 0 | — | 2 |

All three outcomes count toward the attempt denominator.

### radio_status_code distribution (non-SUCCESS rows)

No non-SUCCESS rows in this run.

## 3. Warm-up (first 5 s vs remainder, SUCCESS rows)

| file | warm-up rows | warm-up median m | rest median m | delta m |
|---|---|---|---|---|
| `pucklog_D4DB1C_16.csv` | — | — | — | — |
| `pucklog_D4DB1C_17.csv` | — | — | — | — |

Sanity check for the Methodology §7.2 first-5-s discard rule; large deltas indicate the discard window matters for that file.

## 4. Per-marker statistics (SUCCESS rows)

No SUCCESS rows / no marker-attributable data.

## 5. Deviations and anomalies

- `pucklog_D4DB1C_16.csv`: operator metadata line (line 2) absent — SITE/RUN_ID/TRUE_DISTANCE_M not recorded in file (Methodology §7.4 step incomplete)
- `pucklog_D4DB1C_16.csv`: no data rows (stub file — likely a boot into NORMAL mode with no ranging logged)
- `pucklog_D4DB1C_17.csv`: operator metadata line (line 2) absent — SITE/RUN_ID/TRUE_DISTANCE_M not recorded in file (Methodology §7.4 step incomplete)
- `pucklog_D4DB1C_17.csv`: no data rows (stub file — likely a boot into NORMAL mode with no ranging logged)

![overview](overview.png)
