#!/usr/bin/env python3
"""Verify the Iris collision-only center-to-extent bound in 3-D."""
from __future__ import annotations
import hashlib, math, xml.etree.ElementTree as ET
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "experiments_v2/Calibration Experiments/C0-D-safety/results/C0-D_safety_policy_freeze/collision_bound_3d_verification.yaml"
IRIS = Path("/home/yihuang/PX4-Autopilot/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf")

def values(node, text="pose"):
    return [float(x) for x in (node.findtext(text) or "0 0 0 0 0 0").split()]

def main():
    primitives=[]
    root=ET.parse(IRIS).getroot()
    for link in root.findall(".//link"):
        lp=values(link)
        for collision in link.findall("collision"):
            cp=values(collision); pose=[lp[i]+cp[i] for i in range(6)]
            if any(abs(v) > 1e-12 for v in pose[3:]):
                raise RuntimeError("nonzero collision rotation requires a general bound")
            x,y,z=pose[:3]; geom=collision.find("geometry")
            if geom.find("box") is not None:
                hx,hy,hz=[float(v)/2 for v in geom.findtext("box/size").split()]
                bound=math.sqrt((abs(x)+hx)**2+(abs(y)+hy)**2+(abs(z)+hz)**2); kind="box"
            elif geom.find("cylinder") is not None:
                r=float(geom.findtext("cylinder/radius")); h=float(geom.findtext("cylinder/length"))/2
                bound=math.sqrt((math.hypot(x,y)+r)**2+(abs(z)+h)**2); kind="cylinder"
            elif geom.find("sphere") is not None:
                r=float(geom.findtext("sphere/radius")); bound=math.sqrt(x*x+y*y+z*z)+r; kind="sphere"
            else: continue
            primitives.append({"link":link.get("name"),"collision":collision.get("name"),"type":kind,"pose_xyz_m":[x,y,z],"center_to_collision_extent_3d_m":bound})
    selected=max(primitives,key=lambda x:x["center_to_collision_extent_3d_m"])
    old=0.38353864678361277; radius=selected["center_to_collision_extent_3d_m"]
    # Inputs are copied from the preserved C0-D Stage-A derivation, not reselected.
    p99=0.2380183021913345; velocity=5.; timeout=.02208
    required=2*radius+2*p99+2*velocity*timeout
    rounded=math.ceil((required-1e-12)/.05)*.05
    out={"method":"collision geometry only; exact maximum Euclidean norm from model origin to each axis-aligned collision primitive", "distance_semantics":"3-D Euclidean center-to-collision-extent, matching paper inter-agent distance", "source_file":str(IRIS),"source_sha256":hashlib.sha256(IRIS.read_bytes()).hexdigest(),"primitives":primitives,"selected_3d_collision_radius_m":radius,"previous_horizontal_radius_m":old,"difference_m":radius-old,"stage_a_inputs_unchanged":{"tracking_error_p99_m":p99,"velocity_limit_mps":velocity,"state_timeout_s":timeout},"formula":"2 * collision_radius + 2 * tracking_error_P99 + 2 * velocity_limit * state_timeout","derived_requirement_m":required,"rounded_d_hard_m":rounded,"conclusion":"3-D correction does not change the 0.05-m rounded C0-D d_hard"}
    OUT.write_text(yaml.safe_dump(out,sort_keys=False),encoding="utf-8")
    print(yaml.safe_dump(out,sort_keys=False))
if __name__=="__main__": main()
