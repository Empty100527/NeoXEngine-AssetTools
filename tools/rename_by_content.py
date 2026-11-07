"""Rename _unknown/<hash> files by content sniffing.

- KTX 1.1 container      -> <hash>.ktx
- NeoX object c15941 0d  -> <first-string>.ags (embedded name at offset 12)
- ASCII anim clip        -> <embedded-name>.anim (name = first 32 bytes, null-padded)
"""
import glob
import os
import re
import struct
import sys


def sniff(path):
    with open(path, 'rb') as f:
        head = f.read(64)
    if head[:4] == b'\xabKTX':
        return 'ktx', None
    if head[:4] == b'RGIS':
        return 'gis', None
    if head[:4] == b'\x34\x80\xc8\xbb':
        return 'mesh', None
    if head[:4] == b'\xc1YA\r':
        # NeoX serialized object: u32 size, ... first string at offset 12
        try:
            ln = struct.unpack_from('<I', head, 12)[0]
            if 0 < ln < 40:
                name = head[16:16 + ln].split(b'\x00')[0].decode('ascii', 'replace')
                return 'ags', name
        except struct.error:
            pass
        return 'ags', None
    m = re.match(rb'[a-zA-Z0-9_]{3,32}', head)
    if m:
        name = head[:m.end()].split(b'\x00')[0].decode('ascii', 'replace')
        if head[31:32] == b'\x00' or len(head) >= 32:  # 32-byte padded anim name
            return 'anim', name
        return 'bin', None
    return 'bin', None


def main(roots):
    stats = {}
    for root in roots:
        targets = glob.glob(os.path.join(root, '**', '_unknown', '*'), recursive=True)
        # re-sniff files previously misclassified as .bin
        targets += glob.glob(os.path.join(root, '**', '_unknown', '*.bin'), recursive=True)
        for p in targets:
            if not os.path.isfile(p):
                continue
            if p.endswith('.bin'):
                p2 = p[:-4]
                if os.path.exists(p2):
                    continue
                os.rename(p, p2)
                p = p2
            kind, name = sniff(p)
            stats[kind] = stats.get(kind, 0) + 1
            if name:
                safe = re.sub(r'[^\w\-.]', '_', name)
                new = os.path.join(os.path.dirname(p), f'{safe}.{kind}')
                n = 2
                while os.path.exists(new):
                    base, ext = os.path.splitext(os.path.join(os.path.dirname(p), f'{safe}.{kind}'))
                    new = f'{base}_{n}{ext}'
                    n += 1
            else:
                new = p + f'.{kind}'
            os.rename(p, new)
    print(stats)


if __name__ == '__main__':
    main(sys.argv[1:] or ['unpacked/players', 'unpacked/res', 'unpacked/textures'])
