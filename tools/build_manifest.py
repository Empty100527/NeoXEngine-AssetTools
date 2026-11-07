"""为每个 kit 建立 mtg→贴图映射清单 textures_manifest.json。

- 扫描 unpacked/players/*/  的 .mtg,抽贴图路径(a=diffuse n=normal m=metallic)
- 路径 stem + '.astc' 做 murmur3(0x66666666) → npk id → 检查 textures_png 是否已解码
- 顺带生成套装↔身体配对表(suit_f_XXXX ↔ b_f_XXXX)
"""
import glob
import json
import os
import re
import importlib.util

spec = importlib.util.spec_from_file_location('u', 'unnpk_la.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

PLAYERS = 'unpacked/players'
BS = chr(92)


def tex_id(path_no_ext):
    """尝试多种前缀(npk 相对路径),返回命中的 id,否则返回全长路径的哈希。"""
    v = path_no_ext.replace('/', BS)
    cands = [v]
    for pre in ('character' + BS + 'players' + BS, 'character' + BS, 'res' + BS):
        if v.lower().startswith(pre.lower()):
            cands.append(v[len(pre):])
    ids = [f'{u.murmur3((c + ".astc").encode(), 0x66666666):08X}' for c in cands]
    for i in ids:
        if os.path.exists(os.path.join('textures_png', i + '.png')):
            return i
    return ids[0]


def mtg_textures(kit):
    mp = os.path.join(PLAYERS, kit, f'{kit}.mtg')
    if not os.path.exists(mp):
        return {}
    d = open(mp, 'rb').read()
    out = {}
    for m in re.finditer(rb'[\x20-\x7e]{6,150}\.(?:tga|dds)', d):
        p = m.group().decode()
        base = os.path.basename(p)
        m2 = re.match(r'(.+?)([anm])(?:_\d+)?\.(?:tga|dds)$', base, re.I)
        kind = {'a': 'diffuse', 'n': 'normal', 'm': 'metallic'}.get(m2.group(2).lower()) if m2 else None
        if kind and re.match(r'h_[fm]_\d', base):
            kind = 'head_' + kind  # 头部/头发贴图单独归类
        stem = p[: p.rfind('.')]
        tid = tex_id(stem)
        if kind and os.path.exists(os.path.join('textures_png', tid + '.png')):
            out[kind] = tid
    return out


def main():
    manifest = {}
    kits = sorted(os.path.basename(d) for d in glob.glob(os.path.join(PLAYERS, '*')) if os.path.isdir(d))
    suits, bodies = [], []
    for kit in kits:
        if kit.startswith('_'):
            continue
        tex = mtg_textures(kit)
        if tex:
            manifest[kit] = tex
        if kit.startswith('suit_'):
            suits.append(kit)
        elif kit.startswith('b_'):
            bodies.append(kit)
    pairs = []
    for s in suits:
        num = s.split('_')[-1]
        body = f'b_f_{num}'
        if body in kits or body in bodies:
            pairs.append({'suit': s, 'body': body})
    with open('textures_manifest.json', 'w', encoding='utf-8') as f:
        json.dump({'textures': manifest, 'pairs': pairs}, f, ensure_ascii=False, indent=1)
    print(f'kits带贴图: {len(manifest)}, 套装配对: {len(pairs)}')
    for p in pairs[:10]:
        t = manifest.get(p['suit'], {})
        print(f"  {p['body']} + {p['suit']}  diffuse={t.get('diffuse')} normal={t.get('normal')}")


if __name__ == '__main__':
    main()
