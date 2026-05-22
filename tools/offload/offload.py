#!/usr/bin/env python3
"""offload.py — Post-session offload of SPIFFS CSV logs from a Pack Pucks puck.

The puck firmware (>= v0.7-offload-mode) opens a 3-second mode-select window at
boot. Sending the line "OFFLOAD" during that window switches the puck out of its
normal ranging loop into a quiet state that only services Serial commands
(LIST, DUMP, DELETE, FORMAT). This script automates the host side of that
handshake and pulls all SPIFFS CSV log files into a local session folder.

Workflow:
  1. Open the serial port and wait 200 ms for USB CDC to settle.
  2. Send "OFFLOAD\\n" and watch the boot banner.
  3. Confirm MODE: OFFLOAD; bail out if the puck booted into NORMAL or if no
     banner is seen at all.
  4. LIST the SPIFFS contents (firmware frames the output with
     ---BEGIN LIST--- / ---END LIST--- markers).
  5. DUMP each file; capture the body byte-exact between
     ---BEGIN <name>--- and ---END <name>--- markers.
  6. Write a manifest.txt summarising the banner and per-file outcomes.

Usage:
  python offload.py --port /dev/ttyACM0
  python offload.py --port COM7 --out-dir ./offload --session-id field_2026-05-21
  python offload.py --port /dev/ttyACM0 -v

The puck must be RESET (or unplugged/replugged) immediately before invocation —
the mode-select window only runs once, at boot.

Exit codes:
    0  success — all files OK
    1  partial — some files were size-mismatched or skipped
    2  puck booted into NORMAL mode (script too slow, or firmware predates v0.7)
    3  no boot banner detected (puck unresponsive, or wrong port)
    4  LIST output not framed as expected (firmware version mismatch)
  130  KeyboardInterrupt
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# IST = UTC+5:30. Operators in India enter timestamps in IST; the methodology
# CSV line 2 stores BOOT_UTC in ISO 8601 UTC, so this script converts.
IST_OFFSET = timedelta(hours=5, minutes=30)

try:
    import serial
except ImportError:
    print("This script requires pyserial. Install with: pip install pyserial",
          file=sys.stderr)
    sys.exit(1)


# Per-file outcome labels — kept identical between stdout summary and manifest
# so logs grep cleanly.
ST_OK = "OK"
ST_SIZE_MISMATCH = "SIZE_MISMATCH"
ST_SKIPPED = "SKIPPED"


# ── Serial I/O helpers ──────────────────────────────────────────────────────
def log_rx(line: str, verbose: bool) -> None:
    if verbose:
        print(f"<<< {line}")


def log_tx(cmd: str, verbose: bool) -> None:
    if verbose:
        print(f">>> {cmd}")


def send(ser: "serial.Serial", cmd: str, verbose: bool) -> None:
    """Send a command with a trailing newline. `cmd` must not include one."""
    log_tx(cmd, verbose)
    ser.write((cmd + "\n").encode("utf-8"))
    ser.flush()


def read_line(ser: "serial.Serial", verbose: bool):
    """Read one line. Returns None on timeout (no data). Decoded UTF-8 with
    errors='replace' so CDC enumeration garbage doesn't crash the parser."""
    raw = ser.readline()  # respects ser.timeout
    if not raw:
        return None
    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    log_rx(line, verbose)
    return line


# ── Phase 1: boot banner ────────────────────────────────────────────────────
def parse_banner(ser, verbose, timeout_s=60.0):
    """Wait for the boot banner, send OFFLOAD on the header line, then capture
    the rest. Returns (banner_dict, mode_str_or_None).

    Timing strategy: instead of sending OFFLOAD at startup (which would arrive
    before the puck has even rebooted in most workflows), we wait until the
    "--- Pack Pucks Boot ---" line appears and only then send OFFLOAD. Those
    bytes queue in the puck's USB-CDC RX buffer while the rest of the banner
    is printing; pollForOffloadCommand() picks them up the instant the
    mode-select window opens. The puck therefore never enters NORMAL mode and
    never creates a stub log file for this session.

    The default 60 s timeout gives the user time to plug in the puck (or press
    RST) after starting the script.
    """
    deadline = time.monotonic() + timeout_s
    banner = {}
    in_banner = False
    mode = None
    sent_offload = False
    while time.monotonic() < deadline:
        line = read_line(ser, verbose)
        if line is None:
            continue
        if line == "--- Pack Pucks Boot ---":
            in_banner = True
            # Send OFFLOAD immediately on header — see docstring for why.
            if not sent_offload:
                send(ser, "OFFLOAD", verbose)
                sent_offload = True
            continue
        if line.startswith("-----") and in_banner:
            # Banner closing rule. We return with whatever we collected — even
            # if MODE: line was missing (caller treats mode=None as "no banner").
            return banner, mode
        if in_banner and ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            banner[k] = v
            if k == "MODE":
                mode = v
    return banner, mode


# ── Phase 2: LIST ───────────────────────────────────────────────────────────
def list_files(ser, verbose, timeout_s=5.0):
    """Send LIST and parse the framed response. Returns [(filename, size), ...].
    Raises RuntimeError if framing markers are missing — that signals a
    firmware-version mismatch (pre-v0.7 LIST output was unframed)."""
    send(ser, "LIST", verbose)
    deadline = time.monotonic() + timeout_s
    started = False
    files = []
    while time.monotonic() < deadline:
        line = read_line(ser, verbose)
        if line is None:
            continue
        if line == "---BEGIN LIST---":
            started = True
            continue
        if line == "---END LIST---":
            if not started:
                raise RuntimeError("saw END marker without BEGIN")
            return files
        if started:
            # Format is "<filename> <size_bytes>". Filenames don't contain
            # spaces in our scheme, but rsplit on the last space is defensive.
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    files.append((parts[0], int(parts[1])))
                    continue
                except ValueError:
                    pass
            print(f"Warning: ignoring malformed LIST row: {line!r}",
                  file=sys.stderr)
    raise RuntimeError("timed out waiting for END marker")


# ── Phase 3: DUMP one file ──────────────────────────────────────────────────
def dump_file(ser, fname, expected_size, out_path, verbose,
              begin_timeout_s=2.0, end_timeout_s=30.0):
    """Send DUMP <fname> and capture the body verbatim between markers.

    The firmware emits:
      ---BEGIN <fname>---\\r\\n
      <file bytes, exactly as stored>
      ---END <fname>---\\r\\n

    We read raw bytes (not lines) so the dumped file is byte-exact — line
    endings, trailing newlines, anything else inside the body are preserved.
    """
    send(ser, f"DUMP {fname}", verbose)
    begin_marker = f"---BEGIN {fname}---".encode("utf-8")
    end_marker = f"---END {fname}---".encode("utf-8")

    buf = bytearray()
    log_pos = [0]  # list cell so the inner closure can mutate it

    def maybe_log_lines():
        # In verbose mode, surface any complete lines that have arrived since
        # the last call. In quiet mode, just advance log_pos so we don't grow
        # work unnecessarily.
        if not verbose:
            log_pos[0] = len(buf)
            return
        while True:
            idx = buf.find(b"\n", log_pos[0])
            if idx == -1:
                return
            text = bytes(buf[log_pos[0]:idx]).rstrip(b"\r")
            log_rx(text.decode("utf-8", errors="replace"), True)
            log_pos[0] = idx + 1

    # Phase 3a: wait for BEGIN marker AND its trailing line terminator. We only
    # advance body_start once we have the terminator — otherwise we might
    # include the \r\n in the body when the chunk boundary split it.
    body_start = -1
    deadline = time.monotonic() + begin_timeout_s
    while body_start < 0:
        idx = buf.find(begin_marker)
        if idx != -1:
            post = idx + len(begin_marker)
            if buf[post:post + 2] == b"\r\n":
                body_start = post + 2
                break
            if buf[post:post + 1] == b"\n":
                body_start = post + 1
                break
            # Marker found but its terminator hasn't arrived yet — keep reading.
        if time.monotonic() > deadline:
            print(f"Warning: no BEGIN marker for {fname} within "
                  f"{begin_timeout_s} s — skipping.", file=sys.stderr)
            return ST_SKIPPED, 0
        chunk = ser.read(256)
        if chunk:
            buf.extend(chunk)
            maybe_log_lines()

    # Phase 3b: read until END marker. Body is the slice [body_start:end_idx].
    # 30 s outer is generous: a 50 KB file at CDC's ~10 KB/s effective is ~5 s.
    deadline = time.monotonic() + end_timeout_s
    while True:
        idx = buf.find(end_marker, body_start)
        if idx != -1:
            body = bytes(buf[body_start:idx])
            break
        if time.monotonic() > deadline:
            # Save whatever we have — the operator may want a partial CSV.
            print(f"Warning: no END marker for {fname} within "
                  f"{end_timeout_s} s — saving partial.", file=sys.stderr)
            body = bytes(buf[body_start:])
            break
        chunk = ser.read(256)
        if chunk:
            buf.extend(chunk)
            maybe_log_lines()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(body)
    actual = len(body)
    status = ST_OK if actual == expected_size else ST_SIZE_MISMATCH
    return status, actual


# ── FORMAT helper + unplug countdown ────────────────────────────────────────
def do_format(ser, verbose, timeout_s=15.0):
    """Send FORMAT and stream the firmware's response until 'Done' or timeout.
    Returns True if 'Done' was seen, False otherwise."""
    send(ser, "FORMAT", verbose)
    saw_done = False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = read_line(ser, verbose)
        if line is None:
            continue
        print(line)
        if "Done" in line:
            saw_done = True
            break
    if not saw_done:
        print(f"Warning: no 'Done' confirmation from FORMAT within "
              f"{timeout_s:.0f} s — verify by reconnecting and running LIST.",
              file=sys.stderr)
    return saw_done


def countdown_unplug(seconds=10):
    """Give the operator time to physically unplug the puck before the script
    closes the serial port. Closing the port on ESP32-S3 native USB-CDC
    triggers a chip reset; if the puck reboots into NORMAL with no one
    listening for OFFLOAD, it will create a stub pucklog file on fresh SPIFFS."""
    print()
    print(f"⚠  UNPLUG THE PUCK NOW so it doesn't reboot into NORMAL and "
          f"create a stub file.")
    print(f"   Script will close the port in {seconds} seconds.")
    for i in range(seconds, 0, -1):
        print(f"   {i:2d}...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 40)  # clear the countdown line


# ── Operator metadata (methodology §4.1, §4.4) ──────────────────────────────
# At paper-grade data collection time, line 2 of each CSV is filled in by the
# operator with session context (SITE, SESSION_ID, BOOT_UTC, RUN_ID,
# TRUE_DISTANCE_M) and the file is renamed per the methodology naming
# convention. The firmware can't produce these because it has no RTC, no
# session log, and no ground-truth measurement. This script collects them
# interactively and rewrites each downloaded CSV before the FORMAT prompt.

# Board label is taken from the boot banner's ROLE field directly (full word).
_BOARD_FROM_ROLE = {"INITIATOR": "Initiator", "RESPONDER": "Responder"}


def _split_csv(text):
    """Split a comma-separated input line and trim each field. Returns list."""
    return [p.strip() for p in text.split(",")]


def _ist_to_utc_iso(ist_str):
    """Convert IST timestamp → 'YYYY-MM-DDTHH:MM:SSZ' (UTC).

    Accepts:
      - 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS' (full)
      - 'YYYY-MM-DD HH:MM' (no seconds)
      - 'HH:MM:SS' or 'HH:MM' (date auto-filled with today's IST date)
      - 'NA' (returned unchanged)
    Returns None on parse failure."""
    s = ist_str.strip()
    if s.upper() == "NA":
        return "NA"
    s = s.replace("T", " ")

    dt_ist = None
    # Try full date+time formats first.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt_ist = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    # Fall back to time-only — date auto-fills with today's IST date.
    if dt_ist is None:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(s, fmt).time()
                dt_ist = datetime.combine(datetime.now().date(), t)
                break
            except ValueError:
                continue
    if dt_ist is None:
        return None
    dt_utc = dt_ist - IST_OFFSET
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_boot_seq(safe_name):
    """pucklog_<id>_<boot_seq>.csv → '<boot_seq>'. Returns '' if pattern doesn't match."""
    import re
    m = re.match(r"^pucklog_[0-9A-Fa-f]+_(\d+)\.csv$", safe_name)
    return m.group(1) if m else ""


def _build_new_filename(session_meta, dist_or_run, true_dist, role, safe_name):
    """Methodology §4.4 + per-file disambiguation:
      <DATE>_<SITE>_<TIER>_<distance_or_run>[-<TRUE_DISTANCE_M>]_<BOARD>_<S<n>>_b<boot_seq>.csv

    The TRUE_DISTANCE_M suffix and the boot_seq trailer keep filenames unique
    across multiple boots at the same cone position within a single session."""
    board = _BOARD_FROM_ROLE.get(role, role or "Unknown")
    dist_part = dist_or_run
    if true_dist and true_dist.upper() != "NA":
        dist_part = f"{dist_or_run}-{true_dist}"
    boot_seq = _extract_boot_seq(safe_name)
    suffix = f"_b{boot_seq}" if boot_seq else ""
    return (f"{session_meta['DATE']}_{session_meta['SITE']}_"
            f"{session_meta['TIER']}_{dist_part}_{board}_"
            f"{session_meta['S_NUM']}{suffix}.csv")


def prompt_session_metadata():
    """Prompt once for session-wide values. Re-prompts on missing/wrong-count.
    Returns dict (with auto-derived SESSION_ID) or None if user typed 'skip'."""
    print()
    print("=== Session metadata (once; written to CSV line 2 + used in filenames) ===")
    print("Per methodology §4.1 / §4.4. SESSION_ID is auto-derived as <DATE>_<SITE>_<S<n>>.")
    print("Enter 4 comma-separated values: SITE, TIER, DATE, S<n>")
    print("  DATE = YYYY-MM-DD, or 'today' for current local date.")
    print("  Example: FMAE, T1, today, S1")
    print("Type 'skip' to skip all metadata (flat filenames will be used).")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            return None
        if line.lower() == "skip":
            print("Metadata skipped.")
            return None
        if not line:
            print("Params missing — please enter 4 comma-separated values, or 'skip'.")
            continue
        parts = _split_csv(line)
        if len(parts) != 4:
            print(f"Params missing/extra — got {len(parts)} field(s), need 4. "
                  "Re-enter.")
            continue
        site, tier, date, s_num = parts
        if not all([site, tier, date, s_num]):
            print("Params missing — one or more fields are empty. Re-enter.")
            continue
        if date.lower() == "today":
            date = datetime.now().strftime("%Y-%m-%d")
        session_id = f"{date}_{site}_{s_num}"
        return {"SITE": site, "TIER": tier, "DATE": date, "S_NUM": s_num,
                "SESSION_ID": session_id}


def prompt_file_metadata(safe_name, idx, total, session_meta, role,
                        projected_names, session_dir):
    """Prompt per file. Re-prompts on missing/wrong-count/invalid-IST/overwrite.
    Returns (file_meta dict, new_filename) or (None, None) on 'skip'."""
    print()
    print(f"  Metadata for {safe_name} ({idx}/{total})")
    print("  Enter 3 comma-separated values: "
          "distance_or_run, TRUE_DISTANCE_M, BOOT_UTC_IST")
    print("    distance_or_run: mode label for this recording.")
    print("      - Static tier: distance label like '100m' "
          "(puck stays at that cone for the whole recording).")
    print("      - Mobile tier: run label like 'walk' or 'run-to-200m' "
          "(operator carries the puck while it logs).")
    print("    TRUE_DISTANCE_M: actual ground-truth distance in metres "
          "(laser-measured for static; NA for mobile where a single distance "
          "doesn't apply).")
    print("    BOOT_UTC_IST: 'YYYY-MM-DD HH:MM:SS' or just 'HH:MM:SS' "
          "(today's IST date auto-fills). Script converts to UTC for the CSV.")
    print("    Filename: <date>_<site>_<tier>_<distance_or_run>"
          "[-<TRUE_DISTANCE_M>]_<role>_<S<n>>_b<boot_seq>.csv")
    print("    Examples:")
    print("      100m, 100.0, 10:30:00     (static at the 100m cone)")
    print("      walk, NA, 14:05:00        (mobile walk session)")
    print("  Type 'skip' to skip this file's metadata + rename.")
    while True:
        try:
            line = input("  > ").strip()
        except EOFError:
            return None, None
        if line.lower() == "skip":
            return None, None
        if not line:
            print("  Params missing — enter 3 comma-separated values, or 'skip'.")
            continue
        parts = _split_csv(line)
        if len(parts) != 3:
            print(f"  Params missing/extra — got {len(parts)} field(s), need 3. "
                  "Re-enter.")
            continue
        dist_or_run, true_dist, boot_utc_ist = parts
        if not dist_or_run:
            print("  Params missing — distance_or_run is required. Re-enter.")
            continue
        if not true_dist or not boot_utc_ist:
            print("  Params missing — use NA for unknown TRUE_DISTANCE_M or "
                  "BOOT_UTC_IST. Re-enter.")
            continue
        boot_utc = _ist_to_utc_iso(boot_utc_ist)
        if boot_utc is None:
            print(f"  Invalid BOOT_UTC_IST '{boot_utc_ist}' — use "
                  "'YYYY-MM-DD HH:MM:SS' or 'NA'. Re-enter.")
            continue
        new_name = _build_new_filename(session_meta, dist_or_run, true_dist,
                                       role, safe_name)
        if new_name in projected_names:
            print(f"  Refusing to overwrite: '{new_name}' already assigned to "
                  "another file this run. Choose a different distance_or_run "
                  "or TRUE_DISTANCE_M.")
            continue
        if (session_dir / new_name).exists() and (session_dir / new_name) != \
                (session_dir / safe_name):
            print(f"  Refusing to overwrite: '{new_name}' already exists on disk. "
                  "Choose a different distance_or_run or TRUE_DISTANCE_M.")
            continue
        run_id = f"{session_meta['TIER']}_{dist_or_run}_{session_meta['S_NUM']}"
        return ({"BOOT_UTC": boot_utc, "RUN_ID": run_id,
                 "TRUE_DISTANCE_M": true_dist,
                 "DISTANCE_OR_RUN": dist_or_run}, new_name)


def apply_metadata_and_rename(out_path, session_meta, file_meta, role):
    """Insert operator metadata as CSV line 2 and rename file per methodology
    §4.4. Returns the final Path (or the original if anything fails)."""
    if not out_path.exists():
        return out_path

    # Build the operator metadata line. Firmware uses \r\n; preserve that.
    meta_line = (
        f"# SITE={session_meta['SITE']}, "
        f"SESSION_ID={session_meta['SESSION_ID']}, "
        f"BOOT_UTC={file_meta['BOOT_UTC']}, "
        f"RUN_ID={file_meta['RUN_ID']}, "
        f"TRUE_DISTANCE_M={file_meta['TRUE_DISTANCE_M']}"
    ).encode("utf-8") + b"\r\n"

    data = out_path.read_bytes()
    # Insert immediately after the first line terminator. Firmware writes \r\n
    # via println(), but tolerate \n too in case anything stripped \r.
    idx = data.find(b"\r\n")
    term_len = 2
    if idx == -1:
        idx = data.find(b"\n")
        term_len = 1
    if idx == -1:
        # No newline at all — append at end (defensive; shouldn't happen).
        new_data = data + b"\r\n" + meta_line
    else:
        cut = idx + term_len
        new_data = data[:cut] + meta_line + data[cut:]

    # Compose new filename — same logic the prompt used (board from ROLE,
    # TRUE_DISTANCE_M appended to distance_or_run, boot_seq trailer).
    new_name = _build_new_filename(
        session_meta, file_meta['DISTANCE_OR_RUN'],
        file_meta['TRUE_DISTANCE_M'], role, out_path.name)
    new_path = out_path.parent / new_name

    # Final overwrite safety check — the prompt validated this earlier, but a
    # concurrent process or a same-name retry could have written to new_path
    # between then and now. Refuse rather than clobber.
    if new_path != out_path and new_path.exists():
        print(f"  Refusing to overwrite existing '{new_path.name}' — leaving "
              f"{out_path.name} in place with metadata applied to its current path.",
              file=sys.stderr)
        out_path.write_bytes(new_data)
        return out_path

    new_path.write_bytes(new_data)
    if new_path != out_path:
        try:
            out_path.unlink()
        except OSError:
            pass
    return new_path


# ── Manifest ────────────────────────────────────────────────────────────────
def write_manifest(path, port, baud, banner, results, session_meta=None,
                   file_meta_by_fname=None, renamed_by_fname=None):
    ts = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as f:
        f.write(f"timestamp_utc: {ts}\n")
        f.write(f"port: {port}\n")
        f.write(f"baud: {baud}\n")
        f.write("\n[BANNER]\n")
        for k, v in banner.items():
            f.write(f"{k}: {v}\n")
        if session_meta:
            f.write("\n[SESSION_METADATA]\n")
            for k, v in session_meta.items():
                f.write(f"{k}: {v}\n")
        f.write("\n[FILES]\n")
        for fname, expected, actual, status in results:
            renamed = (renamed_by_fname or {}).get(fname)
            line = (f"{fname}  expected={expected}  actual={actual}  "
                    f"status={status}")
            if renamed:
                line += f"  renamed_to={renamed}"
            f.write(line + "\n")
            fm = (file_meta_by_fname or {}).get(fname)
            if fm:
                for k, v in fm.items():
                    f.write(f"    {k}: {v}\n")


# ── main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="Offload SPIFFS CSV logs from a Pack Pucks puck via USB Serial.")
    ap.add_argument("--port", required=True,
                    help="Serial port (e.g. /dev/ttyACM0, /dev/cu.usbmodem*, COM7).")
    ap.add_argument("--baud", type=int, default=115200,
                    help="Baud rate (default 115200).")
    ap.add_argument("--out-dir", default="./offload",
                    help="Parent directory for session subfolders (default ./offload).")
    ap.add_argument(
        "--session-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Subfolder name under --out-dir (default: current local timestamp).")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Print every received line (<<<) and sent command (>>>).")
    ap.add_argument("--no-metadata", action="store_true",
                    help="Skip operator-metadata prompts (line 2 + file rename). "
                         "Default: prompt for methodology §4.1 / §4.4 metadata.")
    args = ap.parse_args()

    # Defer mkdir until we actually have something to write — otherwise every
    # failed/aborted run (no banner, NORMAL mode, Ctrl-C before first file)
    # leaves an empty session folder behind. dump_file() calls mkdir lazily
    # on the parent path before the first file is written, and we re-create
    # here just before writing the manifest.
    session_dir = Path(args.out_dir) / args.session_id

    # Retry-open: if the port doesn't exist yet, wait for the puck to be
    # plugged in (up to 60 s). When the port does exist, opening it triggers a
    # chip reset on ESP32-S3 native USB-CDC (Windows CDC class driver emits a
    # SET_CONTROL_LINE_STATE that the arduino-esp32 driver maps to soft reset)
    # — which is what we want, since parse_banner() below waits for the
    # resulting boot banner and sends OFFLOAD during the window.
    ser = None
    try:
        ser = serial.Serial(args.port, args.baud,
                            bytesize=8, parity="N", stopbits=1,
                            timeout=0.5,
                            rtscts=False, dsrdtr=False, xonxoff=False)
    except serial.SerialException:
        print(f"Waiting for {args.port} (plug in the puck now)...")
        port_deadline = time.monotonic() + 60.0
        while ser is None:
            time.sleep(0.2)
            try:
                ser = serial.Serial(args.port, args.baud,
                                    bytesize=8, parity="N", stopbits=1,
                                    timeout=0.5,
                                    rtscts=False, dsrdtr=False, xonxoff=False)
            except serial.SerialException as e:
                if time.monotonic() > port_deadline:
                    print(f"Timed out waiting for {args.port}: {e}",
                          file=sys.stderr)
                    return 1

    try:
        # CDC settle: the ESP32-S3 USB CDC interface needs ~200 ms after the
        # host opens the port before bidirectional traffic flows reliably.
        time.sleep(0.2)

        # parse_banner() waits for the "--- Pack Pucks Boot ---" line and only
        # then sends OFFLOAD — see its docstring. The 60 s timeout covers the
        # full reset-and-boot cycle and lets the user manually trigger a
        # reset if reset-on-open didn't fire (rare, but possible).
        print(f"Listening on {args.port} — open will reset the puck; reset "
              f"manually if not.")
        banner, mode = parse_banner(ser, args.verbose, timeout_s=60.0)
        if mode is None:
            print("No boot banner detected. Press RESET or unplug/replug "
                  "while the script is running.", file=sys.stderr)
            return 3
        if mode != "OFFLOAD":
            print("Puck booted into NORMAL mode (script too slow, or firmware "
                  "predates v0.7). Press RESET or unplug/replug and re-run.",
                  file=sys.stderr)
            return 2

        fw = banner.get("FW_VERSION", "?")
        board = banner.get("BOARD_ID", "?")
        role = banner.get("ROLE", "").strip()
        role_label = _BOARD_FROM_ROLE.get(role, role or "Unknown")
        print(f"Banner OK: FW={fw}, BOARD={board}, ROLE={role_label}")

        # Tag session folder with role so Initiator and Responder offloads
        # of the same physical session land in distinct directories.
        session_dir = Path(args.out_dir) / f"{args.session_id}-{role_label}"

        try:
            files = list_files(ser, args.verbose, timeout_s=5.0)
        except RuntimeError as e:
            print(f"LIST output not framed as expected — check firmware "
                  f"version. ({e})", file=sys.stderr)
            return 4

        total_bytes = sum(sz for _, sz in files)
        print(f"LIST: {len(files)} files, total {total_bytes} bytes")

        # Early FORMAT escape hatch — useful when the listed files are known
        # garbage (e.g. wrong firmware version was running) and the operator
        # doesn't want to bother downloading them. Skips the rest of the flow.
        if files:
            try:
                early = input(
                    "Wipe SPIFFS now and exit WITHOUT downloading? "
                    "Type YES to FORMAT immediately, anything else to "
                    "proceed with download: ").strip()
            except EOFError:
                early = ""
            if early == "YES":
                do_format(ser, args.verbose)
                print("SPIFFS wiped. No downloads performed.")
                countdown_unplug(10)
                return 0

        # Methodology §4.1 / §4.4 operator metadata. Prompted once for session
        # values, then per-file during download. Application (insert line 2 +
        # rename) is deferred to after retries so a re-download doesn't clobber
        # already-applied metadata.
        session_meta = None
        file_meta_by_fname = {}
        projected_names = set()  # collision detection across per-file prompts
        if not args.no_metadata and files:
            session_meta = prompt_session_metadata()

        results = []
        for i, (fname, expected) in enumerate(files, start=1):
            # Strip any leading slash for the local filename; the firmware uses
            # a flat namespace anyway and SPIFFS paths with embedded slashes
            # would create unintended subdirectories.
            safe_name = fname.lstrip("/")
            out_path = session_dir / safe_name
            print(f"Downloading {i}/{len(files)}: {safe_name} "
                  f"({expected} bytes)... ", end="", flush=True)
            status, actual = dump_file(ser, fname, expected, out_path,
                                       args.verbose)
            if status == ST_OK:
                print("OK")
            else:
                print(f"{status} (got {actual}, expected {expected})")
            results.append((fname, expected, actual, status))

            # Per-file metadata prompt — only if session metadata was provided
            # and the file actually got written. Cached for use after retries.
            # projected_names is mutated by the prompt on success so subsequent
            # files can't collide; an attempted collision re-prompts that file.
            if session_meta and status != ST_SKIPPED:
                fm, new_name = prompt_file_metadata(
                    safe_name, i, len(files), session_meta, role,
                    projected_names, session_dir)
                if fm:
                    file_meta_by_fname[fname] = fm
                    projected_names.add(new_name)

        # Retry loop for any non-OK files. Transient USB-CDC glitches (a missed
        # END marker, an oversized read window) are usually fixed by a second
        # attempt — the firmware just re-streams the file on the next DUMP.
        while True:
            bad_idx = [i for i, r in enumerate(results) if r[3] != ST_OK]
            if not bad_idx:
                break
            print(f"\n{len(bad_idx)} file(s) did not complete cleanly:")
            for i in bad_idx:
                fname, expected, actual, status = results[i]
                print(f"  {fname.lstrip('/')}  expected={expected}  "
                      f"actual={actual}  status={status}")
            try:
                answer = input("Retry these files? Type YES to retry, "
                               "anything else to keep current results: ").strip()
            except EOFError:
                answer = ""
            if answer != "YES":
                break
            for i in bad_idx:
                fname, expected, _, _ = results[i]
                safe_name = fname.lstrip("/")
                out_path = session_dir / safe_name
                print(f"Retrying {safe_name} ({expected} bytes)... ",
                      end="", flush=True)
                status, actual = dump_file(ser, fname, expected, out_path,
                                           args.verbose)
                if status == ST_OK:
                    print("OK")
                else:
                    print(f"{status} (got {actual}, expected {expected})")
                results[i] = (fname, expected, actual, status)

        any_bad = any(r[3] != ST_OK for r in results)

        # Apply operator metadata + rename for every file that has cached
        # metadata and was actually written to disk. Done after retries so a
        # re-download cannot clobber the line-2 insert.
        renamed_by_fname = {}
        if session_meta and file_meta_by_fname:
            print()
            print("Applying operator metadata (line 2) + renaming files...")
            for fname, _, _, status in results:
                if status == ST_SKIPPED or fname not in file_meta_by_fname:
                    continue
                safe_name = fname.lstrip("/")
                out_path = session_dir / safe_name
                new_path = apply_metadata_and_rename(
                    out_path, session_meta, file_meta_by_fname[fname], role)
                if new_path != out_path:
                    renamed_by_fname[fname] = new_path.name
                    print(f"  {safe_name} → {new_path.name}")
                else:
                    print(f"  {safe_name} (metadata applied; same filename)")

        # Ensure session_dir exists even if zero files were downloaded — we
        # still want a manifest recording what we saw from this puck.
        session_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(session_dir / "manifest.txt", args.port, args.baud,
                       banner, results, session_meta=session_meta,
                       file_meta_by_fname=file_meta_by_fname,
                       renamed_by_fname=renamed_by_fname)

        counts = {ST_OK: 0, ST_SIZE_MISMATCH: 0, ST_SKIPPED: 0}
        bytes_written = 0
        for _, _, actual, status in results:
            counts[status] = counts.get(status, 0) + 1
            bytes_written += actual

        print(f"Done. {len(results)} files, {bytes_written} bytes written. "
              f"OK={counts[ST_OK]} MISMATCH={counts[ST_SIZE_MISMATCH]} "
              f"SKIPPED={counts[ST_SKIPPED]}")

        # Offer to FORMAT the SPIFFS on the puck only if every file came back
        # OK — refuse to wipe data we couldn't fully retrieve. Require literal
        # "YES" to avoid accidental confirms (a stray "y" or Enter does nothing).
        if not any_bad and results:
            try:
                answer = input("All files OK. Format SPIFFS on the puck now? "
                               "Type YES (capitals) to confirm: ").strip()
            except EOFError:
                answer = ""
            if answer == "YES":
                do_format(ser, args.verbose)
                print("SPIFFS wiped.")
                countdown_unplug(10)
            else:
                print("FORMAT skipped.")

        # Exit 0 only when every file is OK. Any mismatch/skip → exit 1 so
        # automation can flag the session for human review without losing data.
        return 0 if not any_bad else 1

    except KeyboardInterrupt:
        # 130 is the shell convention for "killed by SIGINT" (128 + signal 2).
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
