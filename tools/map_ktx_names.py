"""Map unnamed KTX files to texture names by hashing strings found in .mtg/.gim/.mesh files.

The NeoX v2 entry id = murmur3(name, seed) with seed 0x66666666 or 0x77777777.
We harvest candidate strings from material/model files, hash every candidate
under both seeds, and rename matching _unknown/<hex16> / *.ktx files.
"""
import glob
import importlib.util
import os
import re

spec = importlib.util.spec_from_file_location('unnpk_la', 'unnpk_la.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

SEEDS = (0x66666666, 0x77777777)


def harvest_strings(paths, min_len=3, max_len=96):
    pat = re.compile(rb'[\x20-\x7e]{%d,%d}' % (min_len, max_len))
    out = set()
    for p in paths:
        try:
            d = open(p, 'rb').read()
        except OSError:
            continue
        for m in pat.findall(d):
            try:
                out.add(m.decode('ascii'))
            except UnicodeDecodeError:
                pass
    return out


def main():
    ktx = {}  # hexid -> path (from _unknown/<16HEX>.ktx or bare hash files)
    for root in ('unpacked/players', 'unpacked/res', 'unpacked/textures'):
        for p in glob.glob(os.path.join(root, '**', '_unknown', '*.ktx'), recursive=True):
            base = os.path.basename(p)
            hexid = base.split('.')[0]
            if len(hexid) == 16:
                ktx[hexid] = p
    print('unnamed ktx:', len(ktx))

    ref_files = []
    for pat in ('unpacked/script/**', 'unpacked/players/**/*.mtg', 'unpacked/players/**/*.gim',
                'unpacked/players/**/*.mesh', 'unpacked/res/**/*.mtg'):
        ref_files += glob.glob(pat, recursive=True)
    print('reference files:', len(ref_files))

    strings = harvest_strings(ref_files)
    # also with extension guesses and path prefixes
    cands = set()
    for s in strings:
        for v in (s, s.lower(), s.replace('\\', '/')):
            cands.add(v)
            if not v.rsplit('.', 1)[-1].lower() in ('tex', 'tga', 'ktx', 'png', 'dds'):
                for e in ('.tex', '.tga', '.ktx'):
                    cands.add(v + e)
    # hash -> name
    lookup = {}
    for s in cands:
        b = s.encode('ascii', 'ignore')
        for seed in SEEDS:
            h = u.murmur3(b, seed)
            lookup.setdefault(f'{h:08X}', s)
            lookup.setdefault(f'{h:016X}', s)

    hits = 0
    for hexid, path in ktx.items():
        name = None
        if hexid in lookup:
            name = lookup[hexid]
        else:
            short = hexid[8:]  # u32 half
            name = lookup.get(short)
        if name:
            safe = re.sub(r'[^\w\-.]', '_', name)
            newp = os.path.join(os.path.dirname(path), f'{safe}.ktx')
            n = 2
            while os.path.exists(newp):
                newp = os.path.join(os.path.dirname(path), f'{safe}_{n}.ktx')
                n += 1
            os.rename(path, newp)
            hits += 1
    print('matched:', hits, '/', len(ktx))


if __name__ == '__main__':
    main()
