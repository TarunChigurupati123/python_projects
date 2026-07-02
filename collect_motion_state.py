"""
collect_motion_state.py
=======================
Structured-state exporter for the "blender-motion-state-inspection" workflow.

It dumps the facts you need to diagnose twisted / mirrored / foot-sliding /
sunk / mis-scaled characters BEFORE you trust any screenshot:
scene inventory, armature/pose-bone data, forward/up axes, per-frame samples,
and contact + sliding diagnostics.

MUST be run through Blender's own interpreter (bpy is unavailable in system Python):

    blender --background scene.blend --python collect_motion_state.py -- \
        --out motion_state.json --floor 0.0 --samples 12 --armature HeroRig

Everything after the lone "--" is passed to this script, not to Blender.
"""

import bpy
import sys
import json
import argparse
from mathutils import Vector

# ----------------------------------------------------------------------------
# Argument parsing (only args after the "--" separator belong to us)
# ----------------------------------------------------------------------------

def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser(description="Export Blender motion state to JSON.")
    p.add_argument("--out", default="motion_state.json", help="Output JSON path")
    p.add_argument("--floor", type=float, default=0.0, help="World floor Z height")
    p.add_argument("--samples", type=int, default=12,
                   help="How many frames to sample across the timeline")
    p.add_argument("--armature", default=None,
                   help="Name of the armature to analyze (defaults to first found)")
    p.add_argument("--penetration", type=float, default=0.02,
                   help="Foot-below-floor threshold in meters (default 2 cm)")
    p.add_argument("--slide", type=float, default=0.01,
                   help="Planted-foot horizontal movement flagged as sliding (m)")
    return p.parse_args(argv)


# ----------------------------------------------------------------------------
# Small geometry helpers
# ----------------------------------------------------------------------------

def round_vec(v, n=4):
    return [round(float(c), n) for c in v]

def world_bounds(obj):
    """World-space axis-aligned bounding box of an object's local bound_box."""
    mat = obj.matrix_world
    corners = [mat @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]; ys = [c.y for c in corners]; zs = [c.z for c in corners]
    return {
        "min": [round(min(xs), 4), round(min(ys), 4), round(min(zs), 4)],
        "max": [round(max(xs), 4), round(max(ys), 4), round(max(zs), 4)],
    }

def evaluated_mesh_bounds(obj, depsgraph):
    """World-space bounds of the *animated/deformed* mesh at the current frame."""
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    if not mesh.vertices:
        obj_eval.to_mesh_clear()
        return None
    mat = obj_eval.matrix_world
    xs = ys = zs = None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for v in mesh.vertices:
        w = mat @ v.co
        for i in range(3):
            lo[i] = min(lo[i], w[i]); hi[i] = max(hi[i], w[i])
    obj_eval.to_mesh_clear()
    return {"min": [round(x, 4) for x in lo], "max": [round(x, 4) for x in hi]}


# ----------------------------------------------------------------------------
# Semantic bone mapping (loose name heuristics — flags what it can't resolve)
# ----------------------------------------------------------------------------

SEMANTIC_KEYWORDS = {
    "root":     ["root"],
    "pelvis":   ["pelvis", "hips", "hip"],
    "spine":    ["spine", "chest", "torso"],
    "neck":     ["neck"],
    "head":     ["head"],
    "foot.L":   ["foot.l", "foot_l", "leftfoot", "lfoot", "l_foot"],
    "foot.R":   ["foot.r", "foot_r", "rightfoot", "rfoot", "r_foot"],
    "toe.L":    ["toe.l", "toe_l", "lefttoe"],
    "toe.R":    ["toe.r", "toe_r", "righttoe"],
    "knee.L":   ["shin.l", "calf.l", "lowerleg.l", "knee.l"],
    "knee.R":   ["shin.r", "calf.r", "lowerleg.r", "knee.r"],
    "hand.L":   ["hand.l", "hand_l", "lefthand"],
    "hand.R":   ["hand.r", "hand_r", "righthand"],
}

def map_semantic_bones(armature):
    names = [b.name for b in armature.pose.bones]
    lowered = {n.lower(): n for n in names}
    mapping = {}
    for semantic, keys in SEMANTIC_KEYWORDS.items():
        found = None
        for key in keys:
            for low, orig in lowered.items():
                if key in low:
                    found = orig
                    break
            if found:
                break
        mapping[semantic] = found  # may be None -> flagged as missing
    missing = [k for k, v in mapping.items() if v is None]
    return mapping, missing


# ----------------------------------------------------------------------------
# Step 1: scene inventory
# ----------------------------------------------------------------------------

def inventory_scene():
    meshes, armatures, empties, cameras, lights = [], [], [], [], []
    for obj in bpy.data.objects:
        entry = {
            "name": obj.name,
            "parent": obj.parent.name if obj.parent else None,
            "hidden": obj.hide_get() if hasattr(obj, "hide_get") else obj.hide_viewport,
            "world_scale": round_vec(obj.matrix_world.to_scale()),
        }
        if obj.type == "MESH":
            entry["modifiers"] = [m.type for m in obj.modifiers]
            entry["material_slots"] = [s.name for s in obj.material_slots]
            entry["world_bounds"] = world_bounds(obj)
            meshes.append(entry)
        elif obj.type == "ARMATURE":
            entry["bone_count"] = len(obj.pose.bones)
            armatures.append(entry)
        elif obj.type == "EMPTY":
            empties.append(entry)
        elif obj.type == "CAMERA":
            cameras.append(entry)
        elif obj.type == "LIGHT":
            lights.append(entry)
    return {
        "meshes": meshes, "armatures": armatures, "empties": empties,
        "cameras": cameras, "lights": lights,
    }


# ----------------------------------------------------------------------------
# Step 2: skeleton facts
# ----------------------------------------------------------------------------

def describe_skeleton(armature):
    mat = armature.matrix_world
    bones = []
    for pb in armature.pose.bones:
        bones.append({
            "name": pb.name,
            "parent": pb.parent.name if pb.parent else None,
            "head_world": round_vec(mat @ pb.head),
            "tail_world": round_vec(mat @ pb.tail),
            "length": round(pb.length, 4),
            "constraints": [c.type for c in pb.constraints],
        })
    mapping, missing = map_semantic_bones(armature)
    return {"armature": armature.name, "bones": bones,
            "semantic_map": mapping, "missing_semantic": missing}


# ----------------------------------------------------------------------------
# Step 3: forward / up / side axes from the body, not one normal
# ----------------------------------------------------------------------------

def bone_head(armature, name):
    if not name:
        return None
    pb = armature.pose.bones.get(name)
    return armature.matrix_world @ pb.head if pb else None

def estimate_orientation(armature, mapping):
    pelvis = bone_head(armature, mapping.get("pelvis"))
    head = bone_head(armature, mapping.get("head"))
    result = {"world_up": [0, 0, 1]}
    if pelvis and head:
        up_vec = (head - pelvis)
        up_vec.normalize()
        result["body_up_vector"] = round_vec(up_vec)
    # Forward inferred from foot spread cross the up axis (loose but body-based)
    fl = bone_head(armature, mapping.get("foot.L"))
    fr = bone_head(armature, mapping.get("foot.R"))
    if fl and fr and pelvis:
        side = (fl - fr); side.normalize()
        up = Vector((0, 0, 1))
        forward = up.cross(side); forward.normalize()
        result["side_vector_LtoR"] = round_vec(side)
        result["estimated_forward"] = round_vec(forward)
    return result


# ----------------------------------------------------------------------------
# Step 4 + 6: sample frames, record contact and motion facts
# ----------------------------------------------------------------------------

def foot_min_z(obj, depsgraph):
    b = evaluated_mesh_bounds(obj, depsgraph)
    return b["min"][2] if b else None

def sample_frames(scene, armature, char_mesh, mapping, args):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    start, end = scene.frame_start, scene.frame_end
    n = max(2, args.samples)
    frames = sorted(set(int(round(start + (end - start) * i / (n - 1))) for i in range(n)))

    samples = []
    for f in frames:
        scene.frame_set(f)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        row = {"frame": f}
        pelvis = bone_head(armature, mapping.get("pelvis"))
        root = bone_head(armature, mapping.get("root")) or pelvis
        if root:
            row["root_world"] = round_vec(root)
        if pelvis:
            row["pelvis_height"] = round(pelvis.z, 4)
        for side in ("foot.L", "foot.R"):
            fh = bone_head(armature, mapping.get(side))
            if fh:
                row[f"{side}_world"] = round_vec(fh)
                row[f"{side}_clearance"] = round(fh.z - args.floor, 4)
        if char_mesh:
            row["mesh_bounds"] = evaluated_mesh_bounds(char_mesh, depsgraph)
        samples.append(row)
    return samples

def diagnose(samples, args, baseline_bounds):
    findings = []
    # Ground penetration
    for s in samples:
        for side in ("foot.L", "foot.R"):
            clr = s.get(f"{side}_clearance")
            if clr is not None and clr < -args.penetration:
                findings.append({
                    "frame": s["frame"], "type": "ground_penetration",
                    "evidence": f"{side} clearance = {clr} m (< -{args.penetration})",
                })
    # Foot sliding across near-planted frames
    for side in ("foot.L", "foot.R"):
        planted = [s for s in samples if s.get(f"{side}_clearance") is not None
                   and abs(s[f"{side}_clearance"]) < args.penetration]
        for a, b in zip(planted, planted[1:]):
            pa, pb = a[f"{side}_world"], b[f"{side}_world"]
            horiz = ((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2) ** 0.5
            if horiz > args.slide:
                findings.append({
                    "frame": f"{a['frame']}->{b['frame']}", "type": "foot_sliding",
                    "evidence": f"{side} moved {round(horiz,4)} m while planted",
                })
    # Scale drift vs baseline
    if baseline_bounds:
        b0 = baseline_bounds
        base_h = b0["max"][2] - b0["min"][2]
        for s in samples:
            mb = s.get("mesh_bounds")
            if mb and base_h > 0:
                h = mb["max"][2] - mb["min"][2]
                drift = abs(h - base_h) / base_h
                if drift > 0.05:
                    findings.append({
                        "frame": s["frame"], "type": "scale_drift",
                        "evidence": f"height {round(h,3)} vs baseline {round(base_h,3)} ({round(drift*100,1)}%)",
                    })
    return findings


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    args = parse_args()
    scene = bpy.context.scene

    inventory = inventory_scene()

    # Pick the armature
    arm_objs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if args.armature:
        armature = bpy.data.objects.get(args.armature)
    else:
        armature = arm_objs[0] if arm_objs else None

    report = {
        "blend_file": bpy.data.filepath,
        "frame_range": [scene.frame_start, scene.frame_end],
        "unit_scale": round(scene.unit_settings.scale_length, 6),
        "floor_height": args.floor,
        "scene_inventory": inventory,
    }

    if armature is None:
        report["error"] = "No armature found. Pass --armature or check the file."
        write(report, args.out)
        return

    skeleton = describe_skeleton(armature)
    report["skeleton"] = skeleton
    report["orientation"] = estimate_orientation(armature, skeleton["semantic_map"])

    # Best-guess character mesh: heaviest non-hidden mesh parented to / near the rig
    mesh_candidates = [o for o in bpy.data.objects
                       if o.type == "MESH" and not o.hide_get()]
    char_mesh = None
    if mesh_candidates:
        char_mesh = max(mesh_candidates, key=lambda o: len(o.data.vertices))
        report["character_mesh_guess"] = char_mesh.name

    # Baseline: rest pose at frame_start (record before judging motion)
    scene.frame_set(scene.frame_start)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baseline = evaluated_mesh_bounds(char_mesh, depsgraph) if char_mesh else None
    report["baseline_bounds"] = baseline

    samples = sample_frames(scene, armature, char_mesh, skeleton["semantic_map"], args)
    report["frame_samples"] = samples
    report["findings"] = diagnose(samples, args, baseline)

    write(report, args.out)


def write(report, path):
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"[collect_motion_state] wrote {path}")
    print(f"[collect_motion_state] findings: {len(report.get('findings', []))}")


if __name__ == "__main__":
    main()
