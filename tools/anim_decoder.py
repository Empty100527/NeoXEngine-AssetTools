# -*- coding: utf-8 -*-
"""明日之后 (LifeAfter) NeoX 引擎 .anim 动画文件解码器

格式已完全破解（版本 532 文件，占全部 2265 个玩家动画的 95%+）。
旋转 6 字节量化解码公式来自 libclient.so 反汇编（函数 0x9d4514 内
0x9d4f58 分支），并由 .gis 文件中的 float 精度绑定姿态验证：
51 根骨骼解码四元数与绑定姿态完全一致（误差 < 1e-6）。

用法:
    python anim_decoder.py <file.anim>                 # 打印摘要
    python anim_decoder.py <file.anim> --json out.json # 导出完整数据
    python anim_decoder.py <file.anim> --summary-only  # 只打印骨骼/键摘要
    python anim_decoder.py --check <dir-or-glob>       # 批量自检

数据结构:
    AnimData = {
        'name': 动作名, 'root': 根骨名, 'fps': 30,
        'version': 532, 'h1': ..., 'comps': 7,
        'key_count': K, 'times': [毫秒...],
        'bones': [
            {'name': 骨名,
             'position': [[x,y,z] * K],      # 每帧（对 K 个时间点采样）
             'rotation': [[x,y,z,w] * K],    # 四元数, 右手系, 列向量约定
             'scale':    [[sx,sy,sz] * K],
             'static': bool,                  # 骨骼块是否为静态块
             ...}
        ]
    }
"""
import glob
import json
import math
import struct
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

# ---- 旋转量化常量（libclient.so .text 字面量）----
# 23169.767578125 = 32767/sqrt(2), -0.70710677 = -1/sqrt(2)
ROT_K1 = 4.3159689084859565e-05
ROT_K2 = -0.7071067690849304


def decode_rotation6(buf):
    """6 字节量化旋转 -> 单位四元数 (x, y, z, w)。

    位域 (48 bit, 小端):
        [2bit mode][15bit A][15bit B] | [1bit unused][15bit C]
    即前两个 u16 组成 32 位字: mode=A 前 2 位, A 为中 15 位, B 为低 15 位;
    第三个 u16 的低 15 位为 C, 最高位未使用。
    三个分量为 f(x) = x*K1 + K2，取值 [-1/sqrt2, +1/sqrt2]；
    第 4 个分量 = sqrt(1 - A² - B² - C²)（必为最大分量）, 再按 mode 轮转回原位。
    """
    u0, u1, u2 = struct.unpack('<3H', buf)
    w32 = (u0 << 16) | u1
    mode = w32 >> 30
    a = (w32 >> 15) & 0x7fff
    b = w32 & 0x7fff
    c = u2 & 0x7fff
    vals = [a * ROT_K1 + ROT_K2, b * ROT_K1 + ROT_K2, c * ROT_K1 + ROT_K2]
    rem = 1.0 - vals[0] ** 2 - vals[1] ** 2 - vals[2] ** 2
    vals.append(math.sqrt(rem) if rem > 0.0 else 0.0)
    # mode = 被省略(最大)分量的下标; 存储顺序是「轮转后前 3 个」
    shift = (mode + 1) % 4
    q = vals[-shift:] + vals[:-shift] if shift else vals[:]
    n = math.sqrt(sum(x * x for x in q))
    if n <= 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(x / n for x in q)


def decode_scale6(buf):
    """6 字节缩放 -> (sx, sy, sz)，3 个 half float。"""
    return struct.unpack('<3e', buf)


def decode_position12(buf):
    """12 字节平移 -> (x, y, z)，3 个 float32。"""
    return struct.unpack('<3f', buf)


def _slerp(q0, q1, t):
    d = sum(a * b for a, b in zip(q0, q1))
    if d < 0.0:
        q1 = [-x for x in q1]
        d = -d
    if d > 0.9995:
        q = [a + (b - a) * t for a, b in zip(q0, q1)]
        n = math.sqrt(sum(x * x for x in q)) or 1.0
        return [x / n for x in q]
    th = math.acos(max(-1.0, min(1.0, d)))
    s0 = math.sin((1.0 - t) * th)
    s1 = math.sin(t * th)
    s = s0 + s1
    return [(q0[i] * s0 + q1[i] * s1) / s for i in range(4)]


def _lerp3(v0, v1, t):
    return [v0[i] + (v1[i] - v0[i]) * t for i in range(3)]


def _sample(keys, times, target_times, is_quat):
    """keys: [(t, value)]，返回在 target_times 处的采样值列表。"""
    out = []
    ki = 0
    nk = len(keys)
    for tt in target_times:
        if tt <= keys[0][0]:
            out.append(list(keys[0][1]))
            continue
        if tt >= keys[-1][0]:
            out.append(list(keys[-1][1]))
            continue
        while ki < nk - 1 and keys[ki + 1][0] < tt:
            ki += 1
        t0, v0 = keys[ki]
        t1, v1 = keys[ki + 1]
        f = 0.0 if t1 == t0 else (tt - t0) / (t1 - t0)
        if is_quat:
            out.append(_slerp(v0, v1, f))
        else:
            out.append(_lerp3(v0, v1, f))
    return out


def _read_name_table(d, off, count):
    names = []
    for i in range(count):
        raw = d[off + i * 32: off + (i + 1) * 32].split(b'\0')[0]
        names.append(raw.decode('utf-8', 'replace'))
    return names


def parse_anim(path):
    """解析 .anim 文件，返回 AnimData dict。仅支持数据头 version==532。"""
    d = open(path, 'rb').read()
    name = d[0x00:0x20].split(b'\0')[0].decode('utf-8', 'replace')
    root = d[0x20:0x40].split(b'\0')[0].decode('utf-8', 'replace')
    nbone = struct.unpack_from('<H', d, 0x40)[0]
    bones = _read_name_table(d, 0x42, nbone)
    off = 0x42 + nbone * 32
    fps, h1, comps, resv, version, kcount = struct.unpack_from('<IHHIHH', d, off)
    if version not in (532,):
        raise ValueError(f'不支持的 .anim 数据头版本 {version}（本解码器支持 532；'
                         f'版本 6 的文件请用其它工具/等待 v2 支持）')
    times = list(struct.unpack_from('<%df' % kcount, d, off + 16)) if kcount else []
    off += 16 + 4 * kcount
    out_bones = []
    for bi in range(nbone):
        hdr = struct.unpack_from('<I', d, off)[0]
        off += 4
        rec = {'name': bones[bi], 'static': hdr == 0}
        if hdr == 0:
            # 静态块: u16 1 + 12B 平移 + u16 1 + 6B 旋转 + u16 1 + 6B 缩放
            off += 2
            pos0 = decode_position12(d[off:off + 12]); off += 12
            off += 2
            rot0 = decode_rotation6(d[off:off + 6]); off += 6
            off += 2
            scl0 = decode_scale6(d[off:off + 6]); off += 6
            rec.update(position=[list(pos0)] * kcount,
                       rotation=[list(rot0)] * kcount,
                       scale=[list(scl0)] * kcount,
                       counts=(1, 1, 1))
        else:
            c1 = struct.unpack_from('<H', d, off)[0]; off += 2
            pkeys = []
            pkeys_raw = []
            for i in range(c1):
                raw = d[off:off + 12]
                pkeys_raw.append(raw)
                pkeys.append(decode_position12(raw)); off += 12
            c2 = struct.unpack_from('<H', d, off)[0]; off += 2
            rkeys = []
            rkeys_raw = []
            for i in range(c2):
                raw = d[off:off + 6]
                rkeys_raw.append(raw)
                rkeys.append(decode_rotation6(raw)); off += 6
            c3 = struct.unpack_from('<H', d, off)[0]; off += 2
            skeys = []
            skeys_raw = []
            for i in range(c3):
                raw = d[off:off + 6]
                skeys_raw.append(raw)
                skeys.append(decode_scale6(raw)); off += 6
            # 稀疏标志: 共 K 字节, 首字节为通道掩码(0x07), 其余 K-1 字节按时间 1..K-1
            flags = d[off:off + kcount]
            off += kcount
            tail = flags[0] if flags else 0
            body = flags[1:] if kcount > 1 else b''
            p_idx = [0] + [i + 1 for i, f in enumerate(body) if f & 1][:max(0, c1 - 1)]
            r_idx = [0] + [i + 1 for i, f in enumerate(body) if f & 2][:max(0, c2 - 1)]
            s_idx = [0] + [i + 1 for i, f in enumerate(body) if f & 4][:max(0, c3 - 1)]
            p_times = [times[i] if i < len(times) else 0.0 for i in p_idx]
            r_times = [times[i] if i < len(times) else 0.0 for i in r_idx]
            s_times = [times[i] if i < len(times) else 0.0 for i in s_idx]
            rec.update(
                position=_sample(list(zip(p_times, pkeys)), times, times, False) if kcount else [],
                rotation=_sample(list(zip(r_times, rkeys)), times, times, True) if kcount else [],
                scale=_sample(list(zip(s_times, skeys)), times, times, False) if kcount else [],
                counts=(c1, c2, c3), raw_keys=dict(position=pkeys_raw, rotation=rkeys_raw, scale=skeys_raw),
                key_times=dict(position=p_times, rotation=r_times, scale=s_times))
        out_bones.append(rec)
    return dict(path=str(path), name=name, root=root, fps=fps, h1=h1, comps=comps,
                version=version, key_count=kcount, times=times, bones=out_bones,
                end_offset=off, file_size=len(d))


def summarize(anim):
    print(f"== {anim['name']}  (root={anim['root']!r})")
    print(f"   fps={anim['fps']} version={anim['version']} h1={anim['h1']} "
          f"comps={anim['comps']} K={anim['key_count']} 骨数={len(anim['bones'])}")
    print(f"   时间(ms): {[round(t, 2) for t in anim['times'][:12]]}"
          f"{' ...' if anim['key_count'] > 12 else ''}")
    n_static = sum(1 for b in anim['bones'] if b['static'])
    print(f"   静态块 {n_static} / 动画块 {len(anim['bones']) - n_static}")
    for i, b in enumerate(anim['bones']):
        if b['static'] and i > 3:
            continue
        c = b['counts']
        r = b['rotation']
        print(f"   [{i:2d}] {b['name']:20s} static={int(b['static'])} keys(p/r/s)={c} "
              f"rot[0]=({r[0][0]:6.3f},{r[0][1]:6.3f},{r[0][2]:6.3f},{r[0][3]:6.3f})")
        if i >= 4 and not b['static']:
            break


def to_json(anim):
    out = {k: v for k, v in anim.items() if k != 'bones'}
    out['bones'] = []
    for b in anim['bones']:
        nb = {k: b[k] for k in ('name', 'static')}
        for ch in ('position', 'rotation', 'scale'):
            nb[ch] = [[round(x, 7) for x in v] for v in b[ch]]
        nb['counts'] = list(b['counts'])
        out['bones'].append(nb)
    return out


def check_consistency(anim):
    """校验稀疏标志与轨道键数一致。"""
    problems = []
    k = anim['key_count']
    for b in anim['bones']:
        if b['static']:
            continue
        c1, c2, c3 = b['counts']
        if len(b['key_times']['position']) != c1:
            problems.append((b['name'], 'pos', len(b['key_times']['position']), c1))
        if len(b['key_times']['rotation']) != c2:
            problems.append((b['name'], 'rot', len(b['key_times']['rotation']), c2))
        if len(b['key_times']['scale']) != c3:
            problems.append((b['name'], 'scl', len(b['key_times']['scale']), c3))
        for ch in ('position', 'rotation', 'scale'):
            if len(b[ch]) != k:
                problems.append((b['name'], ch + ' samples', len(b[ch]), k))
    return problems


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == '--check':
        pat = args[1] if len(args) > 1 else 'unpacked/players/_unknown/*.anim'
        files = sorted(glob.glob(pat))
        ok = fail = 0
        nprob = 0
        failures = []
        for f in files:
            try:
                a = parse_anim(f)
                probs = check_consistency(a)
                if probs:
                    nprob += 1
                    if len(failures) < 10:
                        failures.append((f, probs[:3]))
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail += 1
                if len(failures) < 10:
                    failures.append((f, repr(e)))
        print(f'files={len(files)} parsed_ok={ok} failed={fail} with_flag_mismatch={nprob}')
        for f, why in failures:
            print('  ', f, why)
        return
    path = args[0]
    anim = parse_anim(path)
    summarize(anim)
    if '--json' in args:
        i = args.index('--json')
        dst = args[i + 1] if i + 1 < len(args) else path + '.json'
        with open(dst, 'w', encoding='utf-8') as fh:
            json.dump(to_json(anim), fh, ensure_ascii=False)
        print(f'wrote {dst}')


if __name__ == '__main__':
    main()
