"""批量导出全部套装: body+suit -> blend/glb (带贴图+蒙皮)。"""
import json
import subprocess
import sys
import time

BLENDER = r"F:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
SCRIPT = r"F:\xwy\IDKWTFFFF\blender_import_lafd.py"

man = json.load(open("textures_manifest.json", encoding="utf-8"))
pairs = man["pairs"]

only = sys.argv[1:] if len(sys.argv) > 1 else None
ok, fail = [], []
t0 = time.time()
for i, p in enumerate(pairs):
    kits = f"{p['body']},{p['suit']}"
    if only and p["suit"] not in only:
        continue
    r = subprocess.run(
        [BLENDER, "--background", "--python", SCRIPT, "--", kits],
        capture_output=True, text=True, timeout=300,
    )
    good = "SAVED" in r.stdout
    (ok if good else fail).append(p["suit"])
    skins = [ln for ln in r.stdout.splitlines() if "SKIN" in ln]
    print(f"[{i+1}/{len(pairs)}] {kits} -> {'OK' if good else 'FAIL'}  {skins[0][:60] if skins else ''}", flush=True)

print(f"完成: 成功 {len(ok)} 失败 {len(fail)}  耗时 {time.time()-t0:.0f}s")
if fail:
    print("失败:", fail)
