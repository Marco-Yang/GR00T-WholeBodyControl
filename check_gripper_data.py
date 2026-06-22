import pandas as pd
import numpy as np
import json
import sys

output_dir = sys.argv[1] if len(sys.argv) > 1 else "outputs/2026-06-22-08-30-30"

df = pd.read_parquet(f"{output_dir}/data/chunk-000/episode_000000.parquet")
print(f"总帧数: {len(df)}")

with open(f"{output_dir}/meta/info.json") as f:
    info = json.load(f)
state_names = info["features"]["observation.state"]["names"]
print(f"observation.state 维度: {len(state_names)}")

hand_indices = {i: name for i, name in enumerate(state_names) if "hand" in name}
print("\n手部关节索引:")
for idx, name in hand_indices.items():
    print(f"  [{idx}] {name}")

first = np.array(df["observation.state"].iloc[0])
last = np.array(df["observation.state"].iloc[-1])
print("\n手部关节角度 第一帧 -> 最后一帧 (变化量):")
for idx, name in hand_indices.items():
    print(f"  {name}: {first[idx]:.4f} -> {last[idx]:.4f}  (delta={last[idx]-first[idx]:.4f})")

hand_idx_list = list(hand_indices.keys())
hand_data = np.stack(df["observation.state"].values)[:, hand_idx_list]
print("\n手部关节角度统计 (min/max/std 跨整段 episode):")
for i, (idx, name) in enumerate(hand_indices.items()):
    col = hand_data[:, i]
    print(f"  {name}: min={col.min():.4f}, max={col.max():.4f}, std={col.std():.4f}")

print("\n--- teleop.left_hand_joints (遥操指令) ---")
lh = np.stack(df["teleop.left_hand_joints"].values)
print(f"  shape: {lh.shape}")
print(f"  min={lh.min(axis=0)}, max={lh.max(axis=0)}, std={lh.std(axis=0).round(4)}")

print("\n--- teleop.right_hand_joints (遥操指令) ---")
rh = np.stack(df["teleop.right_hand_joints"].values)
print(f"  shape: {rh.shape}")
print(f"  min={rh.min(axis=0)}, max={rh.max(axis=0)}, std={rh.std(axis=0).round(4)}")
