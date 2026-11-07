"""把 Capoeira.fbx(Mixamo 骨架)重定向到 LifeAfter 角色骨架上并烘焙。

blender --background --python retarget_capoeira.py
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

# 动态加载角色构建脚本(会建立骨架+蒙皮+贴图)
import sys as _sys
_argv = _sys.argv[_sys.argv.index("--") + 1:] if "--" in _sys.argv else ["b_f_2007,suit_f_2007"]
_sys.argv = ["blender", "--", _argv[0].replace("+", ",")]
exec(open(r"F:/xwy/IDKWTFFFF/blender_import_lafd.py", encoding="utf-8").read())

import mathutils  # noqa: E402

# ---------- 导入 FBX ----------
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=r"F:/xwy/IDKWTFFFF/Capoeira.fbx")
fbx_arm = next(o for o in bpy.data.objects if o not in before and o.type == "ARMATURE")
print(f"FBX armature: {fbx_arm.name}, action: {bpy.data.actions[-1].name}")

# ---------- 骨骼映射 ----------
B = arm_obj.pose.bones  # 我们的角色骨架 pose bones


def pick(*cands):
    for c in cands:
        if c in B:
            return B[c]
    return None


MIX = "mixamorig:"
S = fbx_arm.pose.bones

MAP = []
for src, dst in [
    (MIX + "Hips", "biped_pelvis"),
    (MIX + "Spine", "biped_spine"),
    (MIX + "Spine1", "biped_spine1"),
    (MIX + "Spine2", "biped_spine2"),
    (MIX + "Neck", "biped_neck"),
    (MIX + "Head", "biped_head"),
    (MIX + "LeftShoulder", "biped_l_clavicle"),
    (MIX + "LeftArm", "biped_l_upperarm"),
    (MIX + "LeftForeArm", "biped_l_forearm"),
    (MIX + "LeftHand", "biped_l_hand"),
    (MIX + "LeftHandThumb1", "biped_l_finger0"),
    (MIX + "LeftHandThumb2", "biped_l_finger01"),
    (MIX + "LeftHandIndex1", "biped_l_finger1"),
    (MIX + "LeftHandIndex2", "biped_l_finger11"),
    (MIX + "LeftHandMiddle1", "biped_l_finger2"),
    (MIX + "LeftHandMiddle2", "biped_l_finger21"),
    (MIX + "LeftUpLeg", "biped_l_thigh"),
    (MIX + "LeftLeg", "biped_l_calf"),
    (MIX + "LeftFoot", "biped_l_foot"),
    (MIX + "LeftToeBase", "biped_l_toe0"),
    (MIX + "RightShoulder", "biped_r_clavicle"),
    (MIX + "RightArm", "biped_r_upperarm"),
    (MIX + "RightForeArm", "biped_r_forearm"),
    (MIX + "RightHand", "biped_r_hand"),
    (MIX + "RightHandThumb1", "biped_r_finger0"),
    (MIX + "RightHandThumb2", "biped_r_finger01"),
    (MIX + "RightHandIndex1", "biped_r_finger1"),
    (MIX + "RightHandIndex2", "biped_r_finger11"),
    (MIX + "RightHandMiddle1", "biped_r_finger2"),
    (MIX + "RightHandMiddle2", "biped_r_finger21"),
    (MIX + "RightUpLeg", "biped_r_thigh"),
    (MIX + "RightLeg", "biped_r_calf"),
    (MIX + "RightFoot", "biped_r_foot"),
    (MIX + "RightToeBase", "biped_r_toe0"),
]:
    src_pb = S.get(src)
    dst_pb = B.get(dst)
    if src_pb and dst_pb:
        MAP.append((src_pb, dst_pb))
print(f"MAPPED {len(MAP)} 骨骼对")

# ---------- 帧范围(从源动作曲线取) ----------
act = next(a for a in bpy.data.actions if "mixamo" in a.name)
frames = set()
for layer in getattr(act, "layers", []):
    for strip in getattr(layer, "strips", []):
        for cb in getattr(strip, "channelbags", []):
            for fc in cb.fcurves:
                for k in fc.keyframe_points:
                    frames.add(round(k.co[0]))
FRAMES = sorted(frames)
print(f"帧范围 {FRAMES[0]}..{FRAMES[-1]} ({len(FRAMES)} 帧)")

# ---------- 重定向 ----------
scene = bpy.context.scene
new_act = bpy.data.actions.new("Capoeira")
if not arm_obj.animation_data:
    arm_obj.animation_data_create()
arm_obj.animation_data.action = new_act

# 记录 rest(armature space)
src_rest = {pb.name: pb.matrix.copy() for pb in S}
dst_rest = {pb.name: pb.matrix.copy() for pb in B}

hips_dst = B.get("biped_pelvis")
scene.frame_set(FRAMES[0])
hips_rest_src = S[MIX + "Hips"].matrix.copy()
hips_rest_dst = hips_dst.matrix.copy() if hips_dst else None

import math
print("== rest 朝向差异(度) ==")
for src_pb, dst_pb in MAP:
    A = (fbx_arm.matrix_world @ src_rest[src_pb.name]).to_3x3()
    B = dst_rest[dst_pb.name].to_3x3()
    # 比较 A 与 B 每个轴的夹角
    ang = [math.degrees(A[c].angle(B[c])) for c in range(3)]
    print(f"  {src_pb.name.split(':')[-1]:18s} <- {dst_pb.name:20s} X:{ang[0]:6.1f} Y:{ang[1]:6.1f} Z:{ang[2]:6.1f}")

def _orthonormal3(m3):
    """剥离缩放, 正交化 3x3"""
    import math as _m
    x = mathutils.Vector((m3[0][0], m3[1][0], m3[2][0]))
    y = mathutils.Vector((m3[0][1], m3[1][1], m3[2][1]))
    x = x.normalized()
    y = (y - x * y.dot(x)).normalized()
    z = x.cross(y)
    return mathutils.Matrix((x, y, z)).transposed()

# ---------- 标定: 逐骨 Q = R_dst_rest_world · R_src_rest_world⁻¹ ----------
Q = {}
for src_pb, dst_pb in MAP:
    src_rest_w = fbx_arm.matrix_world @ src_rest[src_pb.name]
    A = _orthonormal3(src_rest_w.to_3x3())
    B = _orthonormal3(dst_rest[dst_pb.name].to_3x3())
    Q[dst_pb.name] = B @ A.inverted()

for f in FRAMES:
    scene.frame_set(f)
    for src_pb, dst_pb in MAP:
        src_pose_w = fbx_arm.matrix_world @ src_pb.matrix
        R_dst = Q[dst_pb.name] @ _orthonormal3(src_pose_w.to_3x3())
        pos = src_pose_w.translation  # 米, 骨架原点一致
        dst_pb.matrix = mathutils.Matrix.LocRotScale(pos, R_dst, None)
    bpy.context.view_layer.update()
    # 烘焙
    for src_pb, dst_pb in MAP:
        dst_pb.keyframe_insert("rotation_quaternion")
        dst_pb.keyframe_insert("location")

print("BAKED 重定向完成")


# ---------- 删除 Mixamo 自带小人(只留我们的角色) ----------
own = set(KITS) | {f"{BASE}_arm", "key"}
for ob in list(bpy.data.objects):
    if ob.name in own:
        continue
    if ob.type in ("MESH", "ARMATURE"):
        bpy.data.objects.remove(ob, do_unlink=True)
    elif ob.type in ("CAMERA", "LIGHT") and not ob.name.startswith("rc"):
        bpy.data.objects.remove(ob, do_unlink=True)

blend_path = OUT / "capoeira_test.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
print(f"SAVED {blend_path}")

# ---------- 渲染验证 3 帧 ----------
import os
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 640
cam = bpy.data.cameras.new("rc")
co = bpy.data.objects.new("rc", cam)
bpy.context.scene.collection.objects.link(co)
co.location = (1.8, -2.6, 1.0)
from mathutils import Vector
d = Vector((0, 0, 0.9)) - co.location
co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
scene.camera = co
for f in (FRAMES[0], FRAMES[len(FRAMES)//2], FRAMES[-1]):
    scene.frame_set(f)
    scene.render.filepath = rf"F:/xwy/IDKWTFFFF/capoeira_f{f}.png"
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED frame {f}")
