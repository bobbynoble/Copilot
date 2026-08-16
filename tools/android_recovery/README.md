# Android Photo/Video Recovery (Forensics Training Tool)

A signature-based file carver for recovering deleted JPEG/PNG/GIF/MP4 files
from a **raw storage image**. Built for a digital forensics coursework
assignment — use it only on devices/media you own or are explicitly
authorized to examine.

## How this works (and why it can't just point at a phone)

Android apps run inside the OS's permission sandbox and cannot read raw
flash blocks — that's what actually makes "undelete" hard on a modern
phone, not a lack of tooling. Deleted-file recovery is only possible once
you have a **raw image** of the storage (a byte-for-byte copy, including
areas the filesystem currently marks as free). This script scans that image
for file signatures — the magic bytes that mark the start of a JPEG/PNG/GIF,
and the box structure of an MP4 — and reconstructs files whose directory
entries were deleted but whose data hasn't been overwritten yet. This is
the same core technique used by tools like PhotoRec, Scalpel, and Autopsy.

## Step 1: Get a raw image to scan

Pick whichever matches your test setup:

- **SD card (easiest, no root needed):** pull the card, read it with a
  card reader on your PC, and image the raw device:
  ```bash
  # Linux — find the device with lsblk first, then:
  sudo dd if=/dev/sdX of=sdcard.img bs=4M status=progress
  ```

- **Android emulator (great for a lab writeup, no hardware needed):**
  locate the AVD's userdata image (e.g.
  `~/.android/avd/<name>.avd/userdata-qemu.img`) and copy it directly — no
  `dd` needed since it's already a file on your host.

- **Rooted test device:** with `adb root` / a shell with root, dump the
  relevant block device (find it under `/dev/block/`) and pull it:
  ```bash
  adb shell "su -c 'dd if=/dev/block/by-name/userdata of=/sdcard/dump.img bs=4M'"
  adb pull /sdcard/dump.img ./dump.img
  ```

- **TWRP recovery:** TWRP can dump partitions directly to an attached OTG
  drive or over `adb pull` from recovery mode, without needing the running
  OS to be rooted.

A stock, non-rooted phone with only USB debugging enabled cannot produce a
full raw image this way — `adb backup`/MTP only exposes the live,
already-visible filesystem, so there's nothing for a carver to recover
beyond what File Manager already shows you.

## Step 2: Run the carver

```bash
python3 tools/android_recovery/recover.py \
  --input sdcard.img \
  --output ./recovered \
  --formats jpg,png,gif,mp4
```

Options:

- `--deep` — scan in smaller overlapping windows; slower but catches more
  fragmented matches. Use this for the final pass in your assignment.
- `--formats` — comma-separated subset of `jpg,png,gif,mp4` (default: all).
- `--yes` — skip the interactive authorization confirmation (for scripted/
  automated runs where you've already confirmed authorization).

Recovered files are written to the output directory as
`recovered_00001_<hash8>.<ext>`, deduplicated by SHA-256 so the same data
carved twice isn't written out twice.

## Limitations (worth noting in your assignment writeup)

- **Fragmentation:** this is a linear carver — it assumes a file's bytes
  are contiguous on disk. Heavily fragmented files (common on
  long-used flash storage) may carve incomplete or corrupted.
- **No filesystem metadata:** original filenames, timestamps, and folder
  paths are gone once the directory entry is deleted; only pixel/video
  data is recoverable this way.
- **Overwritten data is unrecoverable:** if the underlying flash blocks
  have been reused, that portion of the file is permanently gone —
  no software can recover it.
- **Encryption:** most modern Android devices encrypt `/data` at rest
  (FBE). A raw image of an encrypted partition will not carve meaningful
  files unless it's decrypted first (e.g. via TWRP with the correct
  credentials, or a test device with encryption disabled) — this is why
  the SD card / emulator paths above are the most reliable for a lab.

## Verifying it works

The quickest way to sanity-check the carver before pointing it at a real
image: create a small test image, drop a few JPEGs/PNGs into it, delete
them (or just truncate the directory entry) and re-carve:

```bash
dd if=/dev/zero of=test.img bs=1M count=50
# copy a jpg/png into the image via a loopback mount, then delete it
python3 tools/android_recovery/recover.py --input test.img --output ./test_out --yes
```
