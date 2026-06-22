#!/usr/bin/env python3
"""validate_csv.py — structural validator for Pack Pucks pucklog CSVs.

Checks a downloaded (or offloaded + renamed) CSV against the methodology §4 /
FSD DR-1/DR-2 schema:

  line 1   firmware header   (# CSV_SCHEMA_V=..., ROLE=..., FREQ/BW/SF/CR/TXPOWER)
  line 2   operator metadata (# SITE=...) — optional, inserted at offload
  next     column header (role-specific)
  rows     per-cycle records — column count, types, value domains,
           seq strictly +1 from 1, timestamp_ms non-decreasing,
           FR-2.5 consecutive_failures bookkeeping, NaN / rssi=0 conventions.

Errors are schema violations (the file is not trustworthy as-is and must not
gate a SPIFFS FORMAT). Warnings are data-quality flags — e.g. rssi_dbm == 0 on
a SUCCESS row, which is the exact signature of the GetPacketStatus-after-
ranging bug fixed in firmware 0.9-field-hardening.

A truncated final row is a WARNING, not an error: it is the expected artefact
of a sudden power-off between flushes (FR-5.4 bounds the loss; methodology
§1.1 accepts it).

Usage:
    python validate_csv.py <file.csv> [more.csv ...]
Exit codes: 0 = all files pass (warnings allowed), 1 = any error.

Import API (used by offload.py before offering FORMAT):
    validate_file(path)        -> (errors, warnings)   # lists of strings
    validate_text(text, name)  -> (errors, warnings)
"""

import math
import sys
from pathlib import Path

INITIATOR_COLS = ("seq,timestamp_ms,status,raw_distance_m,rssi_dbm,state,"
                  "consecutive_failures,radio_status_code")
RESPONDER_COLS = "seq,timestamp_ms,event,rssi_dbm,state,radio_status_code"

REQUIRED_HDR_KEYS = ("CSV_SCHEMA_V", "FW", "BOARD_ID", "ROLE", "BOOT_MS",
                     "FREQ", "BW", "SF", "CR", "TXPOWER")
SUPPORTED_SCHEMA_V = "1"

INITIATOR_STATUS = {"SUCCESS", "TIMEOUT", "ERROR"}
INITIATOR_STATES = {"BOOT", "RANGING", "DISPLAY", "PEER_LOST", "FAULT"}
RESPONDER_EVENTS = {"BOOT", "READY", "RANGING_REQ", "ERROR"}
RESPONDER_STATES = {"BOOT", "LISTENING", "FAULT"}

# Campaign-locked radio values (FSD §10.3 / methodology §3). Deviations are
# warnings, not errors — the file is still structurally valid, just not from
# the locked Part 1 configuration.
CAMPAIGN_BW_KHZ = (406.25, 1625.0)
CAMPAIGN_SF = 8
CAMPAIGN_FREQ_MHZ = 2400.0


def _parse_kv_comment(line):
    """'# K=V, K=V, ...' -> dict. Tolerates spaces around separators."""
    body = line.lstrip("#").strip()
    out = {}
    for part in body.split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def _check_header(line, errors, warnings):
    """Validate firmware header line 1. Returns ROLE string or None."""
    if not line.startswith("# CSV_SCHEMA_V="):
        errors.append("line 1 is not the firmware header "
                      "(expected '# CSV_SCHEMA_V=...'): %r" % line[:60])
        return None
    kv = _parse_kv_comment(line)
    for key in REQUIRED_HDR_KEYS:
        if key not in kv:
            errors.append(f"header line 1 missing required field {key}= "
                          "(pre-0.7 firmware or corrupted header)")
    if kv.get("CSV_SCHEMA_V") not in (None, SUPPORTED_SCHEMA_V):
        errors.append(f"unsupported CSV_SCHEMA_V={kv['CSV_SCHEMA_V']} "
                      f"(validator supports {SUPPORTED_SCHEMA_V})")
    role = kv.get("ROLE")
    if role not in ("INITIATOR", "RESPONDER"):
        errors.append(f"header ROLE={role!r} is not INITIATOR/RESPONDER")
        role = None
    # Radio-config sanity (warnings — locked campaign values per FSD §10.3)
    try:
        if "BW" in kv and float(kv["BW"]) not in CAMPAIGN_BW_KHZ:
            warnings.append(f"BW={kv['BW']} is not a campaign bandwidth "
                            f"{CAMPAIGN_BW_KHZ} — check the flashed config")
        if "SF" in kv and int(kv["SF"]) != CAMPAIGN_SF:
            warnings.append(f"SF={kv['SF']} differs from campaign SF{CAMPAIGN_SF}")
        if "FREQ" in kv and float(kv["FREQ"]) != CAMPAIGN_FREQ_MHZ:
            warnings.append(f"FREQ={kv['FREQ']} differs from campaign "
                            f"{CAMPAIGN_FREQ_MHZ} MHz")
    except ValueError:
        errors.append("header radio fields (FREQ/BW/SF) are not numeric")
    return role


def _validate_initiator_row(cols, n, prev, errors):
    """prev = dict(seq, ts, cf) carried across rows. Mutated in place."""
    seq_s, ts_s, status, dist_s, rssi_s, state, cf_s, code_s = cols

    if not _is_int(seq_s):
        errors.append(f"row {n}: seq {seq_s!r} not an integer")
    else:
        seq = int(seq_s)
        if seq != prev["seq"] + 1:
            errors.append(f"row {n}: seq {seq} after {prev['seq']} "
                          "(gap or duplicate — DR-1 requires +1 per cycle)")
        prev["seq"] = seq

    if not _is_int(ts_s):
        errors.append(f"row {n}: timestamp_ms {ts_s!r} not an integer")
    else:
        ts = int(ts_s)
        if prev["ts"] is not None and ts < prev["ts"]:
            errors.append(f"row {n}: timestamp_ms {ts} < previous {prev['ts']} "
                          "(must be monotonic)")
        prev["ts"] = ts

    if status not in INITIATOR_STATUS:
        errors.append(f"row {n}: status {status!r} not in {INITIATOR_STATUS}")
        return 0  # remaining checks are status-conditional

    zero_rssi_success = 0
    if status == "SUCCESS":
        try:
            d = float(dist_s)
            if math.isnan(d) or math.isinf(d):
                errors.append(f"row {n}: SUCCESS with non-finite "
                              f"raw_distance_m {dist_s!r}")
        except ValueError:
            errors.append(f"row {n}: SUCCESS raw_distance_m {dist_s!r} "
                          "not a float")
    else:
        if dist_s != "NaN":
            errors.append(f"row {n}: {status} must log raw_distance_m=NaN, "
                          f"got {dist_s!r} (DR-1)")

    if not _is_int(rssi_s):
        errors.append(f"row {n}: rssi_dbm {rssi_s!r} not an integer")
    else:
        rssi = int(rssi_s)
        if status != "SUCCESS" and rssi != 0:
            errors.append(f"row {n}: {status} must log rssi_dbm=0, got {rssi} "
                          "(DR-1)")
        if status == "SUCCESS" and rssi == 0:
            zero_rssi_success = 1

    if state not in INITIATOR_STATES:
        errors.append(f"row {n}: state {state!r} not in {INITIATOR_STATES}")

    if not _is_int(cf_s):
        errors.append(f"row {n}: consecutive_failures {cf_s!r} not an integer")
    else:
        cf = int(cf_s)
        if status == "SUCCESS" and cf != 0:
            errors.append(f"row {n}: SUCCESS must reset "
                          f"consecutive_failures to 0, got {cf} (FR-2.5)")
        elif status == "TIMEOUT" and cf != prev["cf"] + 1:
            errors.append(f"row {n}: TIMEOUT consecutive_failures {cf} != "
                          f"previous {prev['cf']} + 1 (FR-2.5)")
        elif status == "ERROR" and cf != prev["cf"]:
            errors.append(f"row {n}: ERROR must leave consecutive_failures "
                          f"unchanged ({prev['cf']}), got {cf}")
        prev["cf"] = cf

    if not _is_int(code_s):
        errors.append(f"row {n}: radio_status_code {code_s!r} not an integer")
    else:
        code = int(code_s)
        if status == "SUCCESS" and code != 0:
            errors.append(f"row {n}: SUCCESS must log radio_status_code=0, "
                          f"got {code}")
        if status in ("TIMEOUT", "ERROR") and code == 0:
            errors.append(f"row {n}: {status} must log a non-zero "
                          "radio_status_code")
    return zero_rssi_success


def _validate_responder_row(cols, n, prev, errors):
    seq_s, ts_s, event, rssi_s, state, code_s = cols

    if not _is_int(seq_s):
        errors.append(f"row {n}: seq {seq_s!r} not an integer")
    else:
        seq = int(seq_s)
        if seq != prev["seq"] + 1:
            errors.append(f"row {n}: seq {seq} after {prev['seq']} "
                          "(gap or duplicate — DR-2 requires +1 per event)")
        prev["seq"] = seq

    if not _is_int(ts_s):
        errors.append(f"row {n}: timestamp_ms {ts_s!r} not an integer")
    else:
        ts = int(ts_s)
        if prev["ts"] is not None and ts < prev["ts"]:
            errors.append(f"row {n}: timestamp_ms {ts} < previous {prev['ts']} "
                          "(must be monotonic)")
        prev["ts"] = ts

    if event not in RESPONDER_EVENTS:
        errors.append(f"row {n}: event {event!r} not in {RESPONDER_EVENTS}")
        return 0

    zero_rssi_req = 0
    if not _is_int(rssi_s):
        errors.append(f"row {n}: rssi_dbm {rssi_s!r} not an integer")
    else:
        rssi = int(rssi_s)
        if event != "RANGING_REQ" and rssi != 0:
            errors.append(f"row {n}: {event} must log rssi_dbm=0, got {rssi} "
                          "(DR-2)")
        if event == "RANGING_REQ" and rssi == 0:
            zero_rssi_req = 1

    if state not in RESPONDER_STATES:
        errors.append(f"row {n}: state {state!r} not in {RESPONDER_STATES}")

    if not _is_int(code_s):
        errors.append(f"row {n}: radio_status_code {code_s!r} not an integer")
    else:
        code = int(code_s)
        if event == "ERROR" and code == 0:
            errors.append(f"row {n}: ERROR must log a non-zero "
                          "radio_status_code")
        if event != "ERROR" and code != 0:
            errors.append(f"row {n}: {event} must log radio_status_code=0, "
                          f"got {code}")
    return zero_rssi_req


def validate_text(text, name="<csv>"):
    """Validate a pucklog CSV body. Returns (errors, warnings)."""
    errors, warnings = [], []
    truncated_tail = not text.endswith("\n")
    lines = text.splitlines()
    if not lines:
        errors.append("file is empty")
        return errors, warnings

    role = _check_header(lines[0], errors, warnings)

    # Optional operator metadata line (inserted at offload, methodology §4.1).
    i = 1
    if i < len(lines) and lines[i].startswith("#"):
        if not lines[i].startswith("# SITE="):
            warnings.append("line 2 is a comment but not operator metadata "
                            "(expected '# SITE=...')")
        i += 1

    if role is None:
        return errors, warnings  # cannot pick a column schema

    expected_cols = INITIATOR_COLS if role == "INITIATOR" else RESPONDER_COLS
    ncols = expected_cols.count(",") + 1
    if i >= len(lines):
        errors.append("missing column header line")
        return errors, warnings
    if lines[i] != expected_cols:
        errors.append(f"column header mismatch for ROLE={role}: "
                      f"{lines[i]!r}")
        return errors, warnings
    i += 1

    prev = {"seq": 0, "ts": None, "cf": 0}
    zero_rssi = 0
    data_rows = 0
    for n, raw in enumerate(lines[i:], start=1):
        if raw == "":
            continue
        is_last = (i - 1 + n) == len(lines) - 1
        cols = raw.split(",")
        if len(cols) != ncols:
            if is_last and truncated_tail:
                warnings.append(f"row {n}: truncated final row (expected "
                                "after sudden power-off; FR-5.4 bounds the loss)")
            else:
                errors.append(f"row {n}: {len(cols)} columns, expected {ncols}")
            continue
        data_rows += 1
        if role == "INITIATOR":
            zero_rssi += _validate_initiator_row(cols, n, prev, errors)
        else:
            zero_rssi += _validate_responder_row(cols, n, prev, errors)

    if data_rows == 0:
        warnings.append("no data rows (header-only stub — boot with no "
                        "logged cycles)")
    if zero_rssi:
        what = "SUCCESS" if role == "INITIATOR" else "RANGING_REQ"
        warnings.append(f"{zero_rssi}/{data_rows} {what} rows have rssi_dbm=0 "
                        "— signature of the pre-0.9 getRSSI()-after-ranging "
                        "bug; RSSI analysis (C4.4) unusable for this file")
    return errors, warnings


def validate_file(path):
    """Validate a CSV file on disk. Returns (errors, warnings)."""
    p = Path(path)
    try:
        text = p.read_bytes().decode("utf-8", errors="replace")
    except OSError as e:
        return [f"cannot read file: {e}"], []
    return validate_text(text, name=p.name)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    any_error = False
    for arg in argv[1:]:
        errors, warnings = validate_file(arg)
        status = "FAIL" if errors else "PASS"
        print(f"{status}  {arg}  ({len(errors)} error(s), "
              f"{len(warnings)} warning(s))")
        for e in errors:
            print(f"  ERROR: {e}")
        for w in warnings:
            print(f"  warn:  {w}")
        any_error = any_error or bool(errors)
    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
