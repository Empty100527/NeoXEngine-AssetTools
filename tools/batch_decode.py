"""Batch-decode all KTX textures from all npks to PNG. Worker-isolated (segfault-safe)."""
import glob
import os
import struct
import sys
import zipfile
from multiprocessing import Pool
from Crypto.Cipher import AES
import numpy as np
import texture2ddecoder as t2d
from PIL import Image

NPKKEY = bytes.fromhex('606308D8A32C782013D26C2F226F686D')
OUT = r'F:/xwy/IDKWTFFFF/textures_png'

WORKER_NPK = None
WORKER_Z = None


def init_worker(npk_path):
    global WORKER_NPK, WORKER_Z
    WORKER_NPK = npk_path
    WORKER_Z = zipfile.ZipFile(npk_path)


def decode_one(args):
    npk_rel, id_, off, cs, res_flag = args
    f = WORKER_Z.open(npk_rel)
    h = AES.new(NPKKEY, AES.MODE_ECB).decrypt(f.read(32))
    _, magic, ver, toff, n = struct.unpack('<QIIiI', h[:24])
    f.seek(toff)
    table = AES.new(NPKKEY, AES.MODE_ECB).decrypt(f.read(n * 32))
    id_, off, cs, ds, c1, c2, flag, res = struct.unpack_from('<8I', table, id_ * 32)
    f.seek(off)
    data = f.read(cs)
    if len(data) < 68 or data[:4] != b'\xabKTX':
        return (id_, 'too small or not ktx')
    w, hh = struct.unpack_from('<II', data, 36)
    mip0 = struct.unpack_from('<I', data, 64)[0]
    payload = data[68:68 + mip0]
    if mip0 != ((w + 7) // 8) * ((hh + 7) // 8) * 16:
        return (id_, f'size mismatch mip0={mip0} expect={((w+7)//8)*((hh+7)//8)*16} {w}x{hh}')
    out = t2d.decode_astc(payload, w, hh, 8, 8)
    arr = np.frombuffer(bytes(out), dtype=np.uint8).reshape(hh, w, 4)
    img = Image.frombytes('RGBA', (w, hh), bytes(out), 'raw', 'RGBA')
    img.save(os.path.join(OUT, f'{id_:08X}.png'))
    return (id_, 'ok')


def main():
    os.makedirs(OUT, exist_ok=True)
    obb = glob.glob('lifeafter/Android/obb/**/*.obb', recursive=True)[0]
    z = zipfile.ZipFile(obb)
    tasks = []
    meta = {}
    for npk_rel in ['res/character/players.npk', 'res/character/monsters.npk',
                    'res/character/pet.npk', 'res/ui.npk', 'res/textures.npk', 'res.npk']:
        f = z.open(npk_rel)
        h = AES.new(NPKKEY, AES.MODE_ECB).decrypt(f.read(32))
        _, magic, ver, toff, n = struct.unpack('<QIIiI', h[:24])
        f.seek(toff)
        table = AES.new(NPKKEY, AES.MODE_ECB).decrypt(f.read(n * 32))
        for i in range(n):
            id_, off, cs, ds, c1, c2, flag, res = struct.unpack_from('<8I', table, i * 32)
            meta[(npk_rel, i)] = None
            tasks.append((npk_rel, i, off, cs, res))
    print('entries:', len(tasks))
    # group tasks per npk for worker init
    from collections import defaultdict
    bynpk = defaultdict(list)
    for t in tasks:
        bynpk[t[0]].append((t[1], t[2], t[3], t[4]))
    all_tasks = []
    for npk_rel, items in bynpk.items():
        for it in items:
            all_tasks.append((npk_rel, it[0]))
    with Pool(8, initializer=init_worker, initargs=(None,)) as pool:  # init needs npk path
        pass
    # simpler: sequential per npk with pool reinit
    total_ok = 0
    errors = []
    for npk_rel, items in bynpk.items():
        args_list = [(npk_rel, i, off, cs, res) for (i, off, cs, res) in items]
        with Pool(8, initializer=init_worker, initargs=(obb,)) as pool:
            for id_, status in pool.imap_unordered(decode_one, args_list, chunksize=4):
                if status == 'ok':
                    total_ok += 1
                else:
                    errors.append((id_, status))
    print(f'decoded ok: {total_ok}, errors: {len(errors)}')
    for e in errors[:10]:
        print('  ', e)


if __name__ == '__main__':
    main()
