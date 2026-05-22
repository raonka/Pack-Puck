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
from datetime import datetime, timezone
from pathlib import Path

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


# ── Manifest ────────────────────────────────────────────────────────────────
def write_manifest(path, port, baud, banner, results):
    ts = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as f:
        f.write(f"timestamp_utc: {ts}\n")
        f.write(f"port: {port}\n")
        f.write(f"baud: {baud}\n")
        f.write("\n[BANNER]\n")
        for k, v in banner.items():
            f.write(f"{k}: {v}\n")
        f.write("\n[FILES]\n")
        for fname, expected, actual, status in results:
            f.write(f"{fname}  expected={expected}  actual={actual}  "
                    f"status={status}\n")


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
        print(f"Banner OK: FW={fw}, BOARD={board}")

        try:
            files = list_files(ser, args.verbose, timeout_s=5.0)
        except RuntimeError as e:
            print(f"LIST output not framed as expected — check firmware "
                  f"version. ({e})", file=sys.stderr)
            return 4

        total_bytes = sum(sz for _, sz in files)
        print(f"LIST: {len(files)} files, total {total_bytes} bytes")

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

        # Ensure session_dir exists even if zero files were downloaded — we
        # still want a manifest recording what we saw from this puck.
        session_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(session_dir / "manifest.txt", args.port, args.baud,
                       banner, results)

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
                send(ser, "FORMAT", args.verbose)
                # Firmware emits "Formatting SPIFFS..." then
                # "Done. Reboot to re-init logging." — format on a 1.5 MB
                # partition can take a few seconds, so allow up to 15 s.
                saw_done = False
                format_deadline = time.monotonic() + 15.0
                while time.monotonic() < format_deadline:
                    line = read_line(ser, args.verbose)
                    if line is None:
                        continue
                    print(line)
                    if "Done" in line:
                        saw_done = True
                        break
                if not saw_done:
                    print("Warning: no 'Done' confirmation from FORMAT within "
                          "15 s — verify by reconnecting and running LIST.",
                          file=sys.stderr)
                print("SPIFFS wiped. Reset the puck (unplug/replug or RST) "
                      "before the next data session.")
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
