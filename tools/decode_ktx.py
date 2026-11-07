"""Decode one KTX from players.npk (id given) as ASTC; subprocess-isolated."""
import struct
import sys
import glob
import zipfile
from Crypto.Cipher import AES
import numpy as np
import texture2ddecoder as t2d
from PIL import Image

id_want = int(sys.argv[1], 16)
NPKKEY = bytes.fromhex('606308D8A32C782013D26C2F226F686D')
obb = glob.glob('lifeafter/Android/obb/**/*.obb', recursive=True)[0]
z = zipfile.ZipFile(obb)
with z.open('res/character/players.npk') as f:
    h = AES.new(NPKKEY, AES.MODE_ECB).decrypt(f.read(32))
_, magic, ver, toff, n = struct.unpack('<QIIiI', h[:24])
f = z.open('res/character/players.npk')
f.seek(toff)
table = AES.new(NPKKEY, AES.MODE_ECB).decrypt(f.read(n * 32))
for i in range(n):
    id_, off, cs, ds, c1, c2, flag, res = struct.unpack_from('<8I', table, i * 32)
    if id_ == id_want:
        f.seek(off)
        data = f.read(cs)
        break
w, hh = struct.unpack_from('<II', data, 36)
mip0 = struct.unpack_from('<I', data, 64)[0]
payload = data[68:68 + mip0]
bw = int(sys.argv[2]) if len(sys.argv) > 2 else 8
out = t2d.decode_astc(payload, w, hh, bw, bw)
arr = np.frombuffer(bytes(out), dtype=np.uint8).reshape(hh, w, 4)
alpha_bin = ((arr[:, :, 3] == 0) | (arr[:, :, 3] == 255)).mean()
print(f'RESULT {id_want:08X} bw={bw}: uniq={len(np.unique(arr[:, :, :3]))} std={arr[:, :, :3].std():.1f} alpha_bin={alpha_bin:.2f}')
Image.frombytes('RGBA', (w, hh), bytes(out), 'raw', 'RGBA').save(f'tex_{id_want:08X}_bw{bw}.png')
