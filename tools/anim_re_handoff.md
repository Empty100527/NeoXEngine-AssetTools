# 交接文档:明日之后 .anim 动画格式逆向

> 交接方:Claude Code / 接收方:DeepSeek Harness
> 目标:破解 LifeAfter(明日之后)NeoX 引擎 `.anim` 动画文件的量化数值格式,写出可用的 Python 解码器

## 1. 任务目标

写一个 Python 解码器,输入游戏 `.anim` 文件,输出每根骨骼每个关键帧的旋转(欧拉角或四元数)和可选的平移数据。验收标准:解码 `shoot_jump_01_u_01.anim` 等文件,数据导入 Blender 后动作自然合理(配合已就绪的骨架)。

## 2. 环境与文件位置(全部在 F:\xwy\IDKWTFFFF\)

| 路径 | 说明 |
|---|---|
| `unpacked/players/_unknown/*.anim` | 2265 个已解包动画文件(**待破解目标**) |
| `unpacked/res/_unknown/*.anim` | 更多动画(565 个) |
| `anim_structure.py` | Claude 写的时间数组扫描器(可复用/扩展) |
| `unnpk_la.py` | npk 解包器(含 murmur3 哈希实现) |
| `lifeafter/lib/arm64-v8a/libclient.so` | 游戏引擎 so(需要更深逆向时用) |
| `addon_action/neox_action_physics/` | FTthinker 动作插件(内含 acl_decode_210.exe,但游戏数据**不是** ACL 格式) |
| Python | 3.14.64,已装:pycryptodome, lz4, numpy, scipy, texture2ddecoder, capstone, unicorn, bitstring 3.1.9 |

注意:该 Python 无 PySide6;`bitstring` 必须保持 3.1.9(4.x 无 ConstBitStream)。

## 3. 已破解的格式知识(可直接使用)

### 3.1 文件头与骨名表

```
[0x00:0x20]  动作名,32 字节 \0 填充(如 "shoot_jump_01_u_01")
[0x20:0x40]  根骨名,32 字节(如 "biped root")
[0x40:0x42]  u16 骨骼数 N(=51 或 52,与骨架一致)
[0x42:   ]   N × 32 字节骨名表(\0 填充,顺序=骨架骨序)
名表结束偏移 = 0x42 + N*32
```

### 3.2 数据区头(名表结束后,当前实测 shoot_jump_01_u_01)

```
[u32] 帧数 = 30
[u16] 0
[u16] 7          ← 疑似每键分量数(pos3+quat4)
[u32] 0
[u16] 532        ← 含义未明(0x214)
[u16] 动画骨数   ← shoot=14, idle=33(≠总骨数,只有被驱动的骨)
[u8]  0
[3×u8] 0 填充
之后: f32 时间数组(全体轨道共享!)
```

时间数组:K 个 f32,单位毫秒,值全部 ≈ 33.333ms 的倍数(30fps),间距不规则(动画师手 K)。K=该动画最长轨道的键数。扫描定位方法见 `anim_structure.py`。

### 3.3 轨道块(关键发现)

时间数组后是各骨的轨道块。块以 `01 01 00 00` 4 字节标记开头,**+4B 处 u16 = 骨索引**(shoot_jump_01 实测出现 14, 11, 2, 12, 13, 2, 2——注意 bone 2 出现 3 次,可能部分是数据误命中)。

**重大发现:不同轨道格式不同!**
- **bone 11 的块(0x8ee 起,1152B)内含明文 f32 欧拉角关键帧**:每键 3×f32(如 (-0.512, 0.590, -0.003) 弧度),连续排列,无键时间(共享头部时间数组)
- **bone 14 的块(0x6f0 起,510B)是量化数据**:u16 模式 0x4000/0x6000/0xe000/0x0040 高频出现,疑似定点数量化(0x4000=16384=0.5×32768?)

### 3.4 待解问题(按优先级)

1. **轨道块边界与布局**:14 个轨道如何排列?`01 01 00 00` 标记是否每块都有?u16 532 的含义(可能是块大小/偏移/标志)?
2. **量化格式**:bone 14 类块的每键位布局(分量数、每分量位数、范围、是否位流对齐)。线索:块大小 ≈ 每键 31.5B(不规则);高频 u16 模式 0x4000/0x6000/0xe000/0x0040
3. **bone 11 明文轨道为什么是欧拉角而非四元数**——确认分量顺序和单位(弧度)
4. 头部 u16 7(每键分量数)与实际分量数的对应关系

### 3.5 建议的分析方法

- **明文/量化对照**:bone 11(明文)和 bone 14(量化)在同一文件、共享同一时间数组——如果两者驱动相似部位,可对照推量化布局
- **多文件对比**:`coma_02_2.anim` / `coma_02_3.anim` 是同一动作的不同变体;跨文件比较同骨轨道可分离格式常量
- **值域统计**:对量化块按位置 mod N 做直方图,寻找定点数刻度
- **对照引擎**:libclient.so 中有解码代码(arm64),capstone 已装;相关字符串 "npk"、"encrypt_buffer"(PyMethodDef @0x26cccd0 → func 0xb7ad60)
- **验证闭环**:`blender_import_lafd.py` 可构建带骨架的角色(`blender --background --python blender_import_lafd.py -- b_f_2007,suit_f_2007`),解码出的动画套上去渲染帧即可目视验证

## 4. 参考骨架数据

角色骨架 51 骨,名字(空格已转下划线):
```
biped, biped_head, biped_l_calf, biped_l_clavicle, biped_l_finger0, biped_l_finger01,
biped_l_finger1, biped_l_finger11, biped_l_finger2, biped_l_finger21, biped_l_foot,
biped_l_forearm, biped_l_hand, biped_l_thigh, biped_l_toe0, biped_l_upperarm,
biped_neck, biped_pelvis, biped_r_*(同左), biped_root, biped_spine, biped_spine1,
biped_spine2, biped_spineroot, biped_bone00..biped_bone13(饰品/布料骨)
```
.anim 内骨名带空格(如 "biped l calf"),对应时替换为下划线。

## 5. 交付物

1. `anim_decoder.py`:输入 .anim 路径,输出 dict:`{动作名, 帧数, 骨骼[{名, 每键[时间, 旋转(xyz欧拉或四元数), 平移]}]}`
2. 一份格式文档(最终确认的完整布局)
3. (可选)Blender 导入验证脚本

完成后把解码器和文档放到 F:\xwy\IDKWTFFFF\ 下即可,Claude Code 会接手 Blender 导入验证。
