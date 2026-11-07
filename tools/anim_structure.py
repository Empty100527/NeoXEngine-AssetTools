"""扫描 .anim 数据区: 定位所有时间数组与值块边界。"""
import struct
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'unpacked/players/_unknown/shoot_jump_01_u_01.anim'
d = open(path, 'rb').read()

# 名表
nbones = struct.unpack_from('<H', d, 64)[0]
names_end = 66 + nbones * 32

def is_time(f):
    return 16.0 < f < 6000.0 and abs(f * 30 / 1000 - round(f * 30 / 1000)) < 0.05

# 从 names_end 开始按 4 字节步进找"连续递增时间数组"的起点
start = names_end
# 跳过 32B 头
print(f'骨头 {nbones}, 数据区 {start:#x}..{len(d):#x}')
head = d[start:start + 24]
print('头 24B:', head.hex(' '))
frames = struct.unpack_from('<I', head, 0)[0]
u16a, u16b = struct.unpack_from('<HH', head, 4)
u32b = struct.unpack_from('<I', head, 8)[0]
u16c, u16d = struct.unpack_from('<HH', head, 12)
u8e = head[16]
print(f'frames={frames} u16=({u16a},{u16b}) u32={u32b} u16=({u16c},{u16d}) u8={u8e}')

# 扫描: 找所有 run(≥3 连续 f32 时间) —— 步长 4, 从 start+16 到文件尾
runs = []
i = start + 16
while i < len(d) - 4:
    f0 = struct.unpack_from('<f', d, i)[0]
    if is_time(f0):
        # 检查后续是否连续递增时间
        j = i + 4
        cnt = 1
        prev = f0
        while j < len(d) - 4:
            f1 = struct.unpack_from('<f', d, j)[0]
            if is_time(f1) and f1 > prev:
                cnt += 1
                prev = f1
                j += 4
            else:
                break
        if cnt >= 3:
            runs.append((i, cnt, j))
            i = j
            continue
    i += 4

print(f'时间数组数: {len(runs)}')
prev_end = None
for idx, (i, cnt, end) in enumerate(runs):
    gap = (i - prev_end) if prev_end else 0
    times = [struct.unpack_from('<f', d, i + k * 4)[0] for k in range(min(cnt, 3))]
    print(f'track{idx}: times@{i:#x} n={cnt} gap_from_prev={gap}B 首时间={times}')
    prev_end = end
tail = len(d) - runs[-1][2]
print(f'最后值块尾巴: {tail}B')
