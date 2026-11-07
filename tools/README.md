# LifeAfter 解包/导入工具链 (unpacker 分支)

把《明日之后》国际服 1.0.149 的模型/贴图/骨骼动画导出到 Blender 的完整工具链。

> ⚠️ 仅供格式研究与学习。请自行准备合法获取的游戏包体,不要再分发游戏资源。
> 格式文档见 `main` 分支 README 与 `anim_format.md`。

## 依赖

- Python 3.10+(测试于 3.14): `pip install pycryptodome lz4 numpy scipy texture2ddecoder bitstring==3.1.9`
- Blender 4.2+(测试于 5.2): 用于模型导入与动画验证
- NeoXtractor(解析 .mesh): https://github.com/NeoXtractor/NeoXtractor

## 工具清单

| 脚本 | 作用 |
|---|---|
| `unnpk_la.py` | npk 解包器(AES-128-ECB + LZ4,murmur3 文件名还原) |
| `rename_by_content.py` | 按内容嗅探批量改名(anim/ktx/mesh/ags/gis) |
| `anim_decoder.py` | **.anim 动画解码器**(v532,2161 个文件;输出 JSON) |
| `anim_format.md` | .anim 完整格式文档 |
| `build_manifest.py` | 扫描 mtg 生成 贴图↔模型 映射清单 |
| `batch_decode.py` | 批量 KTX→PNG(ASTC 8x8,多进程) |
| `map_ktx_names.py` | 贴图 id ↔ 路径名对照 |
| `blender_import_lafd.py` | Blender 导入: 骨架+蒙皮权重+网格+UV+贴图 |
| `blender_validate_anim.py` | 游戏动画 → 角色上身 → 渲染验证 |
| `retarget_capoeira.py` | Mixamo FBX 动画重定向示例 |
| `export_all.py` | 批量导出全部套装(blend+glb) |

## 快速上手

### 1. 解包 npk(OBB 内)

游戏 OBB 实为 zip,内含 `res/*.npk`。解包:

```bash
python unnpk_la.py <某个.npk> <输出目录>
```

解出的文件名是哈希 id,用内容识别批量改名:

```bash
python rename_by_content.py
```

### 2. 解码贴图

```bash
python batch_decode.py   # → textures_png/
```

### 3. 建立贴图↔模型映射

```bash
python build_manifest.py  # → textures_manifest.json
```

### 4. Blender 导入角色

```bash
blender --background --python blender_import_lafd.py -- b_f_2007,suit_f_2007
```

产出:骨架(51 骨)+蒙皮权重+网格+UV+贴图,`.blend` 保存到 `blender_out/`。

### 5. 套游戏动画

```bash
python anim_decoder.py unpacked/players/_unknown/jump_b_01.anim --json out.json
blender --background --python blender_validate_anim.py -- jump_b_01 0,3,6,9,12
```

`blender_validate_anim.py` 自动: 构建角色 → 解码动画 → 按稀疏标志烘焙关键帧 → 渲染验证帧 → 保存 .blend。

### 6. 批量导出全部套装

```bash
python build_manifest.py && python export_all.py
```

## 已知限制

- 仅支持 version=532 的 .anim(2161/2265);version=6(剧情动画 104 个)轨道布局不同
- 部分 kit 的 mtg 引用的是头部贴图(h_f_*),需与套装 diffuse 区分
- 脚本内路径为作者机器的绝对路径,使用前请按自己的目录调整(搜索 `F:/xwy` 替换)

## 致谢

- 动画格式逆向由 Claude Code 与 DeepSeek Harness 协作完成
- 旋转量化编码定位自 libclient.so 反汇编(`0x9d4514` 函数族)
- 参考项目见 main 分支 README

## 许可

[MIT](../LICENSE)
