# LifeAfter Research (明日之后拆包研究)

网易 NeoX 引擎手游《明日之后》(LifeAfter) 国际服 1.0.149 (2019-10) 的
资源格式逆向研究:npk 容器加密、模型、贴图、骨骼动画格式的分析与工具。

> ⚠️ **仅供格式研究与学习**。本仓库不含任何游戏资源文件,请自行准备合法获取的游戏安装包,
> 且不得使用本项目输出的内容进行商业用途或再分发游戏资源。

## 分支说明

| 分支 | 内容 |
|---|---|
| `main` | 项目总览、格式研究成果、格式文档 |
| `unpacker` | 解包/导入工具链(Python + Blender 脚本) |

## 已破解格式一览

### npk 容器 (v2, 2019 版)

- 头 32B + 文件表(每条 32B = 8×u32)整体 **AES-128-ECB** 加密
  - key `606308D8A32C782013D26C2F226F686D`,IV=0
- 文件名 id = murmur3_x86_32(npk 内相对路径, seed `0x66666666` / `0x77777777`)
- 内容压缩: flag 0=raw / 2=LZ4;script.npk 内容再套一层 AES+zlib(头 16B: i64 flag + i64 size)
- version=3 新版表为 48B/条([LA.NPK.Tool](https://github.com/Ekey/LA.NPK.Tool) 处理的格式)

### 模型 (.mesh, CMesh v3)

- magic `0xBBC88034`;可用 [NeoXtractor](https://github.com/NeoXtractor/NeoXtractor) 的
  `MeshParser0` 完整解析(顶点/法线/UV/面/骨骼/蒙皮权重)
- 骨骼平移在 4×4 绑定矩阵末行,Y-up,单位 ≈ 1/10 米
- 子网格记录 12B/条(v,f,uv,clr 各字段 + `must_be_one=1` 结尾),流紧跟其后

### 贴图 (.ktx)

- **未加密**。标准 KTX1 头(w@36, h@40, mips@52, mip0size@64, data@68)
- ASTC 8x8 压缩,`texture2ddecoder` 或 astcenc 直接解码
- 贴图与材质的对应关系藏在 `.mtg` 二进制值区的完整路径字符串中
  (如 `suit_f_2007\textures\suit_f_2007001a.tga`),
  npk 条目 id = **murmur3(路径去掉原扩展名 + `.astc`, seed 0x66666666)**

### 动画 (.anim)

完整格式见 [`unpacker/anim_format.md`](https://github.com/…/blob/unpacker/anim_format.md)
(v6 头部与轨道标记见分支内文档)。核心要点:

- 头部: 32B 动作名 + 32B 根骨名 + u16 骨数 + 骨名表 + 数据头(fps/分量数/version/键数 K)
- K × f32 时间数组(毫秒,30fps,全体轨道共享)
- 逐骨轨道: 平移 3×f32、旋转 6B 量化四元数(2bit 模式 + 3×15bit,K1=√2/32767,
  K2=-1/√2,省略最大分量用 √(1-Σ) 重建)、缩放 3×f16
- 块尾 K 字节稀疏标志(bit0=平移/bit1=旋转/bit2=缩放)
- version=6 为新变体(剧情/场景动画),轨道以 `01 01 00 00` + u16 骨索引 开头,
  含明文 f32 欧拉轨道与量化轨道两类
- 解码器 `anim_decoder.py` 覆盖 2161/2265 个玩家动画

### 其他发现

- 蒙皮权重就在 NeoXtractor 解析结果里(joints/weights,每顶点 4 骨 + 4 权重)
- 套装↔身体按编号配对(suit_f_XXXX ↔ b_f_XXXX)
- 贴图数据**未加密**(早期"加密"判断是 KTX 头偏移读错的误会)
- npk 头/表的 AES 密钥由 .so 内基钥 `4d408d2d...` 经 3 次 AES 变换派生,
  最终即上表 key(Unicorn 模拟验证)

## 相关项目(致敬/参考)

- [NeoXtractor](https://github.com/NeoXtractor/NeoXtractor) — NeoX npk/模型浏览器
- [Ekey/LA.NPK.Tool](https://github.com/Ekey/LA.NPK.Tool) — 明日之后 npk 解包(新版)
- [ZhangFengze/NeoXResearch](https://github.com/ZhangFengze/NeoXResearch) — NeoX 逆向研究
- [YJBeetle/unnpk](https://github.com/YJBeetle/unnpk) — 阴阳师 npk 解包
- [FTthinker/frxy-neox-blender](https://github.com/FTthinker/frxy-neox-blender) — NeoX Blender 插件

## 许可

[MIT](LICENSE)
