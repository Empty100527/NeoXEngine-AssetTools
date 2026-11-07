"""LifeAfter multi-part mesh -> Blender: mesh + armature + skin weights + textures.

blender --background --python blender_import_lafd.py -- b_f_2007,suit_f_2007
"""
import sys
import types
from pathlib import Path

qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QMessageLogContext = type("QMessageLogContext", (), {})
qtcore.QtMsgType = type("QtMsgType", (), {})
qtcore.qInstallMessageHandler = lambda h: None
pyside = types.ModuleType("PySide6")
pyside.QtCore = qtcore
sys.modules["PySide6"] = pyside
sys.modules["PySide6.QtCore"] = qtcore

import logging
logging.basicConfig(level=logging.WARNING)

NX = Path(r"F:/xwy/IDKWTFFFF/NeoXtractor")
sys.path.insert(0, str(NX))
sys.path.append(r"C:/Users/Administrator/AppData/Local/Python/pythoncore-3.14-64/Lib/site-packages")
from core.mesh_loader.parsers.new_parser import MeshParser0  # noqa: E402

import bpy  # noqa: E402
import mathutils  # noqa: E402
from mathutils import Vector  # noqa: E402

PLAYERS = Path(r"F:/xwy/IDKWTFFFF/unpacked/players")
TEXDIR = Path(r"F:/xwy/IDKWTFFFF/textures_png")
OUT = Path(r"F:/xwy/IDKWTFFFF/blender_out")
OUT.mkdir(exist_ok=True)

# 清掉默认场景
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

_args = sys.argv[sys.argv.index("--") + 1].split(",") if "--" in sys.argv else ["b_f_2007", "suit_f_2007"]
KITS = _args
BASE = KITS[0]
SCALE = 0.1
UV_FLIP = True  # NeoX 为 D3D 风格 UV(原点左上),Blender 需 1-v

# 贴图映射: 优先从 textures_manifest.json 读(mtg 自动解析),否则用内置
try:
    import json as _json
    _man = _json.load(open(r"F:/xwy/IDKWTFFFF/textures_manifest.json", encoding="utf-8"))
    TEXTURES = {k: (v.get("diffuse"), v.get("normal")) for k, v in _man["textures"].items()}
except Exception:
    TEXTURES = {
        "suit_f_2007": ("3664F7C3", "C8966968"),
        "b_f_2007": ("99EA87B1", "6E4D4AC3"),
    }


def neo2bl(v):
    return Vector((v[0] * SCALE, -v[2] * SCALE, v[1] * SCALE))


def parse(kit):
    p = PLAYERS / kit / f"{kit}.mesh"
    return MeshParser0().parse(p.read_bytes())


# ---------- armature from base kit skeleton ----------
parsed = parse(BASE)
mesh, bones = parsed.mesh, parsed.bones
print(f"BASE {BASE}: verts={mesh.vertexes} faces={mesh.faces} bones={bones.count}")

arm_data = bpy.data.armatures.new(f"{BASE}_arm")
arm_obj = bpy.data.objects.new(f"{BASE}_arm", arm_data)
bpy.context.scene.collection.objects.link(arm_obj)
bpy.context.view_layer.objects.active = arm_obj

# NeoX->Blender 坐标基变换 (x,y,z)->(x,-z,y),含 0.1 缩放
C4 = mathutils.Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
C4inv = C4.inverted()

bpy.ops.object.mode_set(mode="EDIT")
created = {}
for i, name in enumerate(bones.names):
    mt = bones.matrix[i]
    M = mathutils.Matrix(list(mt))  # 4x4 行主序 (NeoX 空间)
    Mbl = C4 @ M @ C4inv
    tr = Mbl.translation
    Mbl.translation = (tr.x * SCALE, tr.y * SCALE, tr.z * SCALE)
    eb = arm_data.edit_bones.new(name.replace(" ", "_"))
    eb.matrix = Mbl            # 头部+原始 roll(来自网易绑定矩阵)
    eb.tail = eb.head + (Mbl.to_3x3() @ mathutils.Vector((0, 1, 0))).normalized() * 0.05
    created[i] = eb
children = {}
for i, p in enumerate(bones.parents):
    children.setdefault(p, []).append(i)
for i, eb in created.items():
    kids = children.get(i, [])
    if kids:
        eb.tail = sum((created[k].head for k in kids), Vector()) / len(kids)
    if (eb.tail - eb.head).length < 1e-4:
        eb.tail = eb.head + Vector((0, 0, 0.05))
    par = bones.parents[i]
    if par >= 0 and par in created:
        eb.parent = created[par]
        eb.use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")

bone_names = [n.replace(" ", "_") for n in bones.names]


def make_material(kit):
    diff_id, norm_id = TEXTURES.get(kit, (None, None))
    mat = bpy.data.materials.new(f"{kit}_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if diff_id and (TEXDIR / f"{diff_id}.png").exists():
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(TEXDIR / f"{diff_id}.png"), check_existing=True)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if norm_id and (TEXDIR / f"{norm_id}.png").exists():
            ntex = nt.nodes.new("ShaderNodeTexImage")
            ntex.image = bpy.data.images.load(str(TEXDIR / f"{norm_id}.png"), check_existing=True)
            ntex.image.colorspace_settings.name = "Non-Color"
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_object(kit, mesh_data, skin_bones):
    verts = [neo2bl(p) for p in mesh_data.position]
    faces = [tuple(f) for f in mesh_data.face]
    me = bpy.data.meshes.new(kit)
    me.from_pydata(verts, [], faces)
    me.update()
    me.validate()
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            u, v = mesh_data.uv[me.loops[li].vertex_index]
            uv.data[li].uv = (u, 1.0 - v if UV_FLIP else v)
    me.materials.append(make_material(kit))
    ob = bpy.data.objects.new(kit, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = arm_obj

    # ---- 蒙皮 ----
    joints = getattr(skin_bones, "joints", None) if skin_bones else None
    weights = getattr(skin_bones, "weights", None) if skin_bones else None
    if joints and weights and len(joints) == len(me.vertices):
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = arm_obj
        vgs = {}
        # 关键: 用各部件自己的骨骼名表(不同 kit 骨骼顺序可能不同!)
        kit_bone_names = [n.replace(" ", "_") for n in skin_bones.names]
        for vi in range(len(me.vertices)):
            for j, w in zip(joints[vi], weights[vi]):
                if j == 255 or w <= 0:
                    continue
                name = kit_bone_names[j] if j < len(kit_bone_names) else f"bone_{j}"
                vg = vgs.get(name)
                if vg is None:
                    vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
                    vgs[name] = vg
                vg.add([vi], w, "REPLACE")
        nweighted = sum(1 for jlist in joints if any(jj != 255 for jj in jlist))
        print(f"SKIN {kit}: {nweighted}/{len(me.vertices)} 顶点已绑骨, {len(vgs)} 个顶点组")
    else:
        print(f"SKIN {kit}: 无权重数据")
    print(f"PART {kit}: verts={mesh_data.vertexes} faces={mesh_data.faces}")
    return ob


for kit in KITS:
    p2 = parse(kit)
    skin = p2.bones  # 各部件自带权重(骨骼序与 base 骨架一致)
    build_object(kit, p2.mesh, skin)

# 灯光
light = bpy.data.lights.new("key", type="SUN")
light.energy = 3
lo = bpy.data.objects.new("key", light)
bpy.context.scene.collection.objects.link(lo)
lo.rotation_euler = (0.6, 0, 0.8)

import os
tag = "_".join(KITS)
blend_path = OUT / tag / f"{tag}.blend"
os.makedirs(os.path.dirname(blend_path), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
try:
    bpy.ops.export_scene.gltf(filepath=str(OUT / tag / f"{tag}.glb"), export_format="GLB")
except Exception as e:
    print("GLB export fail:", e)
print(f"SAVED {blend_path}")
