# -*- coding: utf-8 -*-
"""Blender 验证: 导入角色 (b_f_2007+suit_f_2007) 并套用 anim_decoder 解码的 .anim 动画。

用法:
  blender --background --python blender_validate_anim.py -- atk_run_01_u 0,4,8,12,16
参数: 动画名(不含扩展名), 要渲染的帧号(逗号分隔, 从 0 开始的时间点下标)
输出: anim_check_<name>_f<idx>.png 与 .blend
"""
import sys

_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["atk_run_01_u", "0,4,8,12,16"]
ANIM_NAME = _argv[0]
FRAMES = [int(x) for x in _argv[1].split(",")] if len(_argv) > 1 else [0, 5, 10, 15]
KITS = _argv[2] if len(_argv) > 2 else "b_f_2007,suit_f_2007"
sys.argv = ["blender", "--", KITS]
sys.path.insert(0, r"F:/xwy/IDKWTFFFF")
exec(open(r'F:/xwy/IDKWTFFFF/blender_import_lafd.py', encoding='utf-8').read())

import numpy as np
import bpy
import mathutils
from mathutils import Vector
from anim_decoder import parse_anim

ANIM_PATH = rf"F:/xwy/IDKWTFFFF/unpacked/players/_unknown/{ANIM_NAME}.anim"
anim = parse_anim(ANIM_PATH)
print(f"ANIM {anim['name']} K={anim['key_count']} fps={anim['fps']} bones={len(anim['bones'])}")
print("times:", [round(t, 2) for t in anim['times']])

mesh_bone_names = [n.replace(' ', '_') for n in bones.names]
parent_of = {}
for i, p in enumerate(bones.parents):
    parent_of[mesh_bone_names[i]] = mesh_bone_names[p] if p >= 0 else None

arm_obj = bpy.data.objects.get(BASE + '_arm')
assert arm_obj, 'no armature'

anim_index = {}
for i, b in enumerate(anim['bones']):
    anim_index[b['name'].replace(' ', '_')] = i

order, seen = [], set()


def visit(nm):
    if nm in seen:
        return
    p = parent_of.get(nm)
    if p and p in mesh_bone_names:
        visit(p)
    seen.add(nm)
    order.append(nm)


for nm in mesh_bone_names:
    visit(nm)

C4np = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)
C4inv_np = np.linalg.inv(C4np)
C4 = mathutils.Matrix(C4np.tolist())
C4inv = C4.inverted()
SCALE = 0.1


def q2m(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def local_row(bone_rec, k):
    t = np.array(bone_rec['position'][k], dtype=float)
    q = bone_rec['rotation'][k]
    s = np.array(bone_rec['scale'][k], dtype=float)
    Rrow = q2m(q).T
    L = np.eye(4)
    L[0, :3] = s[0] * Rrow[0]
    L[1, :3] = s[1] * Rrow[1]
    L[2, :3] = s[2] * Rrow[2]
    L[3, :3] = t
    return L


def world_matrices(k):
    W = {}
    for nm in order:
        ai = anim_index.get(nm)
        if ai is None:
            W[nm] = None
            continue
        L = local_row(anim['bones'][ai], k)
        p = parent_of.get(nm)
        W[nm] = L if (p is None or W.get(p) is None) else L @ W[p]
    return W


def neox_row_to_blender(Wrow):
    """行主序 NeoX 世界矩阵(行向量约定) -> Blender 骨架空间变换 (D*C4) M^T (D*C4)^-1,
    D=diag(0.1,0.1,0.1,1)。该变换直接作用在骨骼蒙皮矩阵上。"""
    Wt = Wrow.T
    Mbl = C4np @ Wt @ C4inv_np
    Mbl[0:3, 3] *= SCALE
    return Mbl


# 绑定姿态(Blender 骨架空间) = 导入脚本里 edit_bone.matrix 的构造方式
Mbl_bind = {}
for i, nm in enumerate(mesh_bone_names):
    Wbind = np.array(bones.matrix[i], dtype=float).reshape(4, 4)
    Mbl_bind[nm] = neox_row_to_blender(Wbind)

# --- 设置 pose 关键帧 ---
bpy.context.view_layer.objects.active = arm_obj
arm_obj.select_set(True)
bpy.ops.object.mode_set(mode='POSE')
K = anim['key_count']
rest_mat = {nm: np.array(arm_obj.pose.bones[nm].bone.matrix_local) for nm in order if nm in arm_obj.pose.bones}
for k in range(K):
    W = world_matrices(k)
    delta = {}
    for nm in order:
        if W.get(nm) is None or nm not in rest_mat:
            continue
        Mbl_anim = neox_row_to_blender(W[nm])
        delta[nm] = Mbl_anim @ np.linalg.inv(Mbl_bind[nm])
    for nm in order:
        pb = arm_obj.pose.bones.get(nm)
        if pb is None or nm not in delta:
            continue
        B = rest_mat[nm]
        pname = parent_of.get(nm)
        Dp = delta.get(pname) if pname else None
        local = (np.linalg.inv(Dp) @ delta[nm]) if Dp is not None else delta[nm]
        basis = np.linalg.inv(B) @ local @ B
        pb.matrix_basis = mathutils.Matrix(basis.tolist())
    for nm in order:
        pb = arm_obj.pose.bones.get(nm)
        if pb is None or nm not in delta:
            continue
        pb.keyframe_insert('location', frame=k + 1)
        pb.keyframe_insert('rotation_quaternion', frame=k + 1)
        pb.keyframe_insert('scale', frame=k + 1)
bpy.ops.object.mode_set(mode='OBJECT')

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = K
scene.render.fps = int(anim['fps'])
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024

cam = bpy.data.cameras.new("cam")
co = bpy.data.objects.new("cam", cam)
bpy.context.scene.collection.objects.link(co)
co.location = (2.2, -3.0, 1.0)
d = Vector((0, 0, 0.85)) - co.location
co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
scene.camera = co

for k in FRAMES:
    if k < K:
        W = world_matrices(k)
        pts = {nm: W[nm][3, :3] for nm in ('biped_l_hand', 'biped_r_hand', 'biped_l_foot', 'biped_r_foot') if W.get(nm) is not None}
        print(f'FRAME {k} world pos:', {nm: [round(float(x), 3) for x in v] for nm, v in pts.items()})

for k in FRAMES:
    if k >= K:
        continue
    scene.frame_set(k + 1)
    out = rf'F:/xwy/IDKWTFFFF/anim_check_{ANIM_NAME}_f{k:03d}.png'
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print('RENDERED', out)

blend_path = rf'F:/xwy/IDKWTFFFF/blender_out/anim_{ANIM_NAME}.blend'
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print('SAVED', blend_path)
