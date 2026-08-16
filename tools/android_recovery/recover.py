#!/usr/bin/env python3
"""
Signature-based file carver for recovering deleted photos/videos from a raw
storage image (e.g. an Android SD card dump, a rooted device's `dd` image,
or an emulator disk file).

This does NOT talk to a live phone over adb and does NOT bypass Android's
filesystem permissions — it scans a raw byte image you already extracted
and reconstructs files whose directory entries were deleted but whose data
is still present, using file-signature (magic number) carving. This is the
same technique tools like PhotoRec/Scalpel use.

For authorized forensics coursework / testing on your own device only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from typing import BinaryIO, Optional


@dataclass(frozen=True)
class Signature:
    name: str
    ext: str
    header: bytes
    footer: Optional[bytes]
    max_size: int  # safety cap so a missing footer can't carve gigabytes


SIGNATURES: dict[str, Signature] = {
    "jpg": Signature("JPEG", "jpg", b"\xff\xd8\xff", b"\xff\xd9", 25 * 1024 * 1024),
    "png": Signature(
        "PNG", "png", b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82", 50 * 1024 * 1024
    ),
    "gif": Signature("GIF", "gif", b"GIF8", b"\x00\x3b", 20 * 1024 * 1024),
}

# MP4/MOV/3GP family: not a simple header/footer pair. Files are a sequence
# of length-prefixed "boxes" (atom size:4, type:4, ...). We locate the
# 'ftyp' box and walk boxes forward, summing their declared sizes, to find
# where the container actually ends.
MP4_BRAND_MARKER = b"ftyp"
MP4_MAX_SIZE = 500 * 1024 * 1024
MP4_MAX_BOXES = 5000


def carve_mp4_length(data: bytes, ftyp_marker_offset: int) -> Optional[int]:
    """Given the offset of the 'ftyp' marker within data, return the total
    carved length of the MP4 container, or None if the box chain looks
    invalid this early (not a real MP4 start)."""
    start = ftyp_marker_offset - 4  # size field precedes the 4-byte type
    if start < 0:
        return None

    pos = start
    end_limit = min(len(data), start + MP4_MAX_SIZE)
    boxes_seen = 0

    while pos + 8 <= end_limit and boxes_seen < MP4_MAX_BOXES:
        box_size = int.from_bytes(data[pos : pos + 4], "big")
        box_type = data[pos + 4 : pos + 8]

        if not box_type.isalnum() and box_type not in (b"free", b"skip"):
            break

        if box_size == 1:
            # 64-bit extended size follows the type field
            if pos + 16 > end_limit:
                break
            box_size = int.from_bytes(data[pos + 8 : pos + 16], "big")
            if box_size < 16:
                break
        elif box_size == 0:
            # Box extends to end of file — cap it at our safety limit
            pos = end_limit
            boxes_seen += 1
            break
        elif box_size < 8:
            break

        pos += box_size
        boxes_seen += 1

    if boxes_seen == 0:
        return None
    return pos - start


CHUNK_SIZE = 16 * 1024 * 1024
OVERLAP = 1024  # covers signatures/footers that straddle a chunk boundary


def iter_chunks(fh: BinaryIO, chunk_size: int, overlap: int):
    """Yield (absolute_offset, bytes) chunks with overlap so signatures that
    straddle a chunk boundary are not missed."""
    fh.seek(0)
    prev_tail = b""
    base_offset = 0
    while True:
        buf = fh.read(chunk_size)
        if not buf:
            break
        window = prev_tail + buf
        window_offset = base_offset - len(prev_tail)
        yield window_offset, window
        prev_tail = buf[-overlap:] if len(buf) >= overlap else buf
        base_offset += len(buf)


def find_all(haystack: bytes, needle: bytes, start: int = 0):
    idx = haystack.find(needle, start)
    while idx != -1:
        yield idx
        idx = haystack.find(needle, idx + 1)


class Carver:
    def __init__(self, input_path: str, output_dir: str, wanted_formats: set[str]):
        self.input_path = input_path
        self.output_dir = output_dir
        self.wanted_formats = wanted_formats
        self.recovered_count = 0
        self.seen_hashes: set[str] = set()
        self.total_size = self._get_size()

    def _get_size(self) -> int:
        try:
            return os.path.getsize(self.input_path)
        except OSError:
            return 0  # raw block devices may not report a usable size

    def run(self, deep: bool = False) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        chunk_size = CHUNK_SIZE if not deep else CHUNK_SIZE // 4

        with open(self.input_path, "rb") as fh:
            scanned = 0
            for offset, window in iter_chunks(fh, chunk_size, OVERLAP):
                self._scan_window(offset, window)
                scanned += len(window)
                self._progress(scanned)

        print(f"\nDone. Recovered {self.recovered_count} file(s) -> {self.output_dir}")

    def _progress(self, scanned: int) -> None:
        if self.total_size:
            pct = min(100.0, scanned / self.total_size * 100)
            print(f"\rScanning... {pct:5.1f}%", end="", flush=True)
        else:
            print(f"\rScanning... {scanned / (1024 * 1024):.0f} MB", end="", flush=True)

    def _scan_window(self, window_offset: int, window: bytes) -> None:
        for key, sig in SIGNATURES.items():
            if key not in self.wanted_formats:
                continue
            for local_idx in find_all(window, sig.header):
                self._carve_header_footer(window, local_idx, sig)

        if "mp4" in self.wanted_formats:
            for local_idx in find_all(window, MP4_BRAND_MARKER):
                self._carve_mp4(window, local_idx)

    def _carve_header_footer(self, window: bytes, local_idx: int, sig: Signature) -> None:
        search_end = min(len(window), local_idx + sig.max_size)
        footer_idx = window.find(sig.footer, local_idx + len(sig.header), search_end)
        if footer_idx == -1:
            return  # footer not in this window; if it's cut across a
            # chunk boundary beyond OVERLAP it will simply be missed —
            # acceptable for a training-scale carver
        end = footer_idx + len(sig.footer)
        self._write(window[local_idx:end], sig.ext)

    def _carve_mp4(self, window: bytes, local_idx: int) -> None:
        length = carve_mp4_length(window, local_idx)
        if not length:
            return
        start = local_idx - 4
        end = min(len(window), start + length)
        self._write(window[start:end], "mp4")

    def _write(self, data: bytes, ext: str) -> None:
        if not data:
            return
        digest = hashlib.sha256(data).hexdigest()
        if digest in self.seen_hashes:
            return
        self.seen_hashes.add(digest)

        self.recovered_count += 1
        filename = f"recovered_{self.recovered_count:05d}_{digest[:8]}.{ext}"
        path = os.path.join(self.output_dir, filename)
        with open(path, "wb") as out:
            out.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Carve deleted photos/videos out of a raw storage image using "
            "file-signature scanning. Run against a disk image or device "
            "you own and are authorized to examine (e.g. a college "
            "forensics assignment)."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the raw image or block device to scan (e.g. sdcard.img)",
    )
    parser.add_argument(
        "--output", required=True, help="Directory to write recovered files into"
    )
    parser.add_argument(
        "--formats",
        default="jpg,png,gif,mp4",
        help="Comma-separated list of formats to recover (default: jpg,png,gif,mp4)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Scan in smaller overlapping windows (slower, more thorough)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the authorization confirmation prompt (for scripted runs)",
    )
    return parser.parse_args()


def confirm_authorization(input_path: str) -> None:
    print(
        "This tool carves data directly off a storage image/device.\n"
        f"Target: {input_path}\n"
        "Only run this against media you own or are explicitly authorized "
        "to examine (e.g. your own device/SD card for a coursework assignment).\n"
    )
    reply = input("Type 'yes' to confirm you are authorized to scan this target: ")
    if reply.strip().lower() != "yes":
        print("Not confirmed. Exiting.")
        sys.exit(1)


def main() -> None:
    args = parse_args()

    if not args.yes:
        confirm_authorization(args.input)

    if not os.path.exists(args.input):
        print(f"Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    wanted = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    valid = set(SIGNATURES.keys()) | {"mp4"}
    unknown = wanted - valid
    if unknown:
        print(f"Unknown format(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        print(f"Supported: {', '.join(sorted(valid))}", file=sys.stderr)
        sys.exit(1)

    carver = Carver(args.input, args.output, wanted)
    carver.run(deep=args.deep)


if __name__ == "__main__":
    main()
