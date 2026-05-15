"""Tiny disk write/read benchmark for E: drive. ~64 MB sequential."""
import os
import time

PATH = r'E:\options_scanner\data\.disk_bench.tmp'
SIZE_MB = 64
CHUNK = 1024 * 1024  # 1 MB

data = b'\x5a' * CHUNK

# Write
t0 = time.time()
with open(PATH, 'wb') as f:
    for _ in range(SIZE_MB):
        f.write(data)
    f.flush()
    os.fsync(f.fileno())
write_sec = time.time() - t0

# Drop OS cache by reopening
# Read
t0 = time.time()
total = 0
with open(PATH, 'rb') as f:
    while True:
        chunk = f.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
read_sec = time.time() - t0

os.remove(PATH)

print('size_mb={} write_sec={:.2f} read_sec={:.2f} write_mb_per_sec={:.1f} read_mb_per_sec={:.1f}'.format(
    SIZE_MB, write_sec, read_sec, SIZE_MB / write_sec, SIZE_MB / read_sec))
