"""LifeAfter (NeoX engine) NPK unpacker - v2 format (2019, 1.0.149 era).

Header (32B, AES-128-ECB): u64 hash | u32 magic 'NXPK' | i32 version | u32 tableOff | i32 fileCount
Table   (fileCount x 32B, AES-128-ECB): u64 hash | u32 off | u32 csize | u32 dsize |
                                        u32 crc | u32 crc | u32 flag | u32 reserved
flag: 0=raw, 2=LZ4 block. script.npk raw entries with non-0x4974 magic are AES+zlib wrapped.
Entry name: murmur3_32(path, seedA=0x66666666) << 32 | murmur3_32(path, seedB=0x77777777)
"""
import io
import os
import struct
import sys
import zipfile
import zlib
from Crypto.Cipher import AES
import lz4.block

KEY = bytes.fromhex('606308D8A32C782013D26C2F226F686D')
SEED_A, SEED_B = 0x66666666, 0x77777777
MASK32 = 0xFFFFFFFF

# ---------- murmur3_x86_32 (matches NpkHash.cs) ----------
C1, C2 = 0xCC9E2D51, 0x1B873593

def _rol(x, r):
    return ((x << r) | (x >> (32 - r))) & MASK32

def murmur3(data: bytes, seed: int) -> int:
    h = seed & MASK32
    nblocks = len(data) // 4
    for i in range(nblocks):
        k = struct.unpack_from('<I', data, i * 4)[0]
        k = (k * C1) & MASK32
        k = _rol(k, 15)
        k = (k * C2) & MASK32
        h ^= k
        h = _rol(h, 13)
        h = (h * 5 + 0xE6546B64) & MASK32
    tail = data[nblocks * 4:]
    if tail:
        k = int.from_bytes(tail, 'little')
        k = (k * C1) & MASK32
        k = _rol(k, 15)
        k = (k * C2) & MASK32
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & MASK32
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & MASK32
    h ^= h >> 16
    return h

# ---------- name map ----------
def load_names(list_path):
    by_ab, by_a, by_b = {}, {}, {}
    with open(list_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            name = line.strip()
            if not name:
                continue
            win = name.replace('/', '\\')
            ha, hb = murmur3(win.encode('ascii', 'ignore'), SEED_A), murmur3(win.encode('ascii', 'ignore'), SEED_B)
            by_ab[(ha << 32) | hb] = name
            by_a.setdefault(ha, name)
            by_b.setdefault(hb, name)
    return by_ab, by_a, by_b

# ---------- unpack ----------
def unpack(npk_stream, out_dir, names, verbose=False):
    """names = (by_ab, by_a, by_b) — v2 entries store a single u32 id."""
    header_enc = npk_stream.read(32)
    h = AES.new(KEY, AES.MODE_ECB).decrypt(header_enc)
    _hash, magic, version, table_off, file_count = struct.unpack('<QIIiI', h[:24])
    if magic != 0x4B50584E:
        raise ValueError(f'bad magic {magic:#x}')
    table_size = file_count * 32
    npk_stream.seek(table_off)
    table = bytearray(npk_stream.read(table_size))
    table = AES.new(KEY, AES.MODE_ECB).decrypt(bytes(table))

    os.makedirs(out_dir, exist_ok=True)
    named = unknown = 0
    for i in range(file_count):
        e_hash, e_off, e_csize, e_dsize, _crc1, _crc2, flag, _res = \
            struct.unpack_from('<8I', table, i * 32)
        npk_stream.seek(e_off)
        data = npk_stream.read(e_csize)
        if flag == 2:
            data = lz4.block.decompress(data, uncompressed_size=e_dsize)
        elif flag != 0:
            data = zlib.decompress(data)

        # script.npk inner AES layer
        base = os.path.basename(getattr(npk_stream, 'name', '') or '')
        if base == 'script.npk' and flag == 0 and len(data) % 16 == 0:
            data = AES.new(KEY, AES.MODE_ECB).decrypt(data)
            inner_flag, inner_size = struct.unpack_from('<qq', data, 0)
            if inner_flag == 1:
                data = zlib.decompress(data[16:16 + inner_size])
            else:
                data = data[16:16 + inner_size]

        name = names[0].get(e_hash) or names[1].get(e_hash) or names[2].get(e_hash)
        if name is None:
            unknown += 1
            name = f'_unknown/{e_hash:016X}'
        else:
            named += 1
        path = os.path.join(out_dir, name.replace('\\', os.sep).replace('/', os.sep))
        path = os.path.abspath(path)
        if not path.startswith(os.path.abspath(out_dir)):
            continue  # path traversal guard
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        if verbose:
            print(f'  {e_hash:016X} -> {name} ({len(data)} B)')
    return named, unknown


def main():
    obb = glob_one('lifeafter/Android/obb/**/*.obb')
    names_ab, names_a, names_b = load_names('LA.NPK.Tool/LA.Unpacker/LA.Unpacker/Projects/FileNames.list')
    z = zipfile.ZipFile(obb)
    targets = sys.argv[1:] or ['res/character/test-camera.npk']
    for t in targets:
        out = os.path.join('unpacked', os.path.splitext(os.path.basename(t))[0])
        print(f'== {t} -> {out}')
        with z.open(t) as f:
            # attach npk name for script.npk special-case
            f.name = os.path.basename(t)
            named, unknown = unpack(f, out, (names_ab, names_a, names_b))
        print(f'   named={named} unknown={unknown}')


def glob_one(pat):
    import glob as g
    return g.glob(pat, recursive=True)[0]


if __name__ == '__main__':
    main()
