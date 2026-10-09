"""Import Packages"""
import cv2
import os
import shutil
import csv

from sklearn.cluster import KMeans
from charset_normalizer import detect
from roboflow import Roboflow
from ultralytics import YOLO
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd
import numpy as np
import supervision as sv

"""Extract frames from home video"""
# cap = cv2.VideoCapture(r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV")
# os.makedirs("frames", exist_ok=True)
# frame_count = 0
# saved = 0
#
# while cap.isOpened():
#     ret, frame = cap.read()
#     if not ret:
#         break
#     if frame_count % 15 == 0:           # every 15th frame
#         cv2.imwrite(f"frames/frame_{saved:04d}.jpg", frame)
#         saved += 1
#     frame_count += 1
#
# cap.release()
# print(f"Extracted {saved} frames")


"""Used Roboflow to annotate ping pong ball and created frame dataset"""
# rf = Roboflow(api_key=os.environ["ROBOFLOW_API_KEY"])
# project = rf.workspace("infinitelightnings-workspace").project("ping-pong-ball-vrt4c")
# version = project.version(3)
# dataset = version.download("yolov8")

"""Training"""
# Paths
# DATA_YAML   = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Code\Ping-Pong-Ball-3\data.yaml"
# SAVE_DIR    = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App/Models"
# RUN_NAME    = "pingpong_ball_v1"

#Train
# model = YOLO("yolov8s.pt")          # pretrained COCO weights as starting point
#
# results = model.train(
#     data=DATA_YAML,
#     epochs=50,
#     imgsz=1280,
#     batch=8,                        # drop to 4 for out-of-memory errors
#     name=RUN_NAME,
#     patience=15,                    # stops early if val loss doesn't improve
#     save=True,
#     save_period=10,                 # checkpoint every 10 epochs
#     val=True,
#     plots=True,                     # saves loss/mAP curves to results folder
# )
#
# #Save best model to project folder
# best_weights = os.path.join("runs", "detect", "pingpong_ball_v1-2", "weights", "best.pt")
# os.makedirs(SAVE_DIR, exist_ok=True)
# destination  = os.path.join(SAVE_DIR, "pingpong_ball_v1.pt")
#
# shutil.copy(best_weights, destination)
# print(f"Best model saved to: {destination}")
#
# #Quick validation on test set
# print("\nRunning validation on test set...")
# test_results = model.val(
#     data=DATA_YAML,
#     split="test",
#     imgsz=1280,
# )
#
# print(f"\nmAP@0.5:      {test_results.box.map50:.3f}")
# print(f"mAP@0.5-0.95: {test_results.box.map:.3f}")
# print(f"Precision:    {test_results.box.mp:.3f}")
# print(f"Recall:       {test_results.box.mr:.3f}")

"""Quick Testing"""
# model = YOLO(r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Code\runs\detect\pingpong_ball_v1-2\weights\best.pt")
# results = model.predict(r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV",save=True)

"""Ball Interpolation"""
# MODEL_PATH = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Code\runs\detect\pingpong_ball_v1-2\weights\best.pt"
# VIDEO_PATH = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV"
# RAW_OUTPUT = r"ball_positions_raw.csv"   # save raw detections here first
#
# model = YOLO(MODEL_PATH)
# cap   = cv2.VideoCapture(VIDEO_PATH)
#
# #Inference loop — saves directly to CSV as it runs
# with open(RAW_OUTPUT, 'w', newline='') as f:
#     writer = csv.writer(f)
#     writer.writerow(['frame', 'x', 'y'])     # header
#
#     frame_num = 0
#     while cap.isOpened():
#         ret, frame = cap.read()
#         if not ret:
#             break
#
#         results = model(frame, conf=0.3, imgsz=1280)[0]
#
#         ball = None
#         for i, cls in enumerate(results.boxes.cls):
#             if int(cls) == 0:
#                 x1, y1, x2, y2 = results.boxes.xyxy[i].tolist()
#                 ball = [(x1 + x2) / 2, (y1 + y2) / 2]
#                 break
#
#         # Write directly to file each frame — nothing lost if script crashes
#         if ball:
#             writer.writerow([frame_num, ball[0], ball[1]])
#         else:
#             writer.writerow([frame_num, None, None])
#
#         frame_num += 1
#         if frame_num % 500 == 0:
#             print(f"Processed {frame_num} frames...")   # progress indicator
#
# cap.release()
# print(f"Raw detections saved to {RAW_OUTPUT}")
#
# #Load raw detections
# df = pd.read_csv('ball_positions_raw.csv')
#
# #Interpolate gaps
# df['x'] = pd.to_numeric(df['x'], errors='coerce')
# df['y'] = pd.to_numeric(df['y'], errors='coerce')
#
# df['x'] = df['x'].interpolate(method='linear', limit=10)
# df['y'] = df['y'].interpolate(method='linear', limit=10)
#
# df.to_csv('ball_positions_interpolated.csv', index=False)
# print(f"Done — {len(df)} frames, {df['x'].notna().sum()} with ball position")

"""Finding Table Coordinates"""
# VIDEO_PATH = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV"
#
# #Grab first frame
# cap = cv2.VideoCapture(VIDEO_PATH)
# ret, frame = cap.read()
# cap.release()
#
# if not ret:
#     print("ERROR: Could not read video")
#     exit()
#
# # Convert BGR to RGB for matplotlib display
# frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#
# #Click handler
# clicks = []
# labels = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"]
#
# fig, ax = plt.subplots(figsize=(14, 8))
# ax.imshow(frame_rgb)
# ax.set_title("Click the 4 table corners in order:\n"
#              "1) Top-Left  2) Top-Right  3) Bottom-Right  4) Bottom-Left",
#              fontsize=11)
#
# def on_click(event):
#     if event.xdata is None or event.ydata is None:
#         return
#     if len(clicks) >= 4:
#         return
#
#     x, y = int(event.xdata), int(event.ydata)
#     clicks.append((x, y))
#
#     # Draw point and label
#     ax.plot(x, y, 'go', markersize=10)
#     ax.annotate(f"{len(clicks)}: {labels[len(clicks)-1]}\n({x}, {y})",
#                 xy=(x, y), xytext=(x + 20, y - 20),
#                 color='lime', fontsize=9,
#                 arrowprops=dict(arrowstyle='->', color='lime'))
#     fig.canvas.draw()
#
#     if len(clicks) == 4:
#         print("\n── Copy this into your next script ──────────────────")
#         print("TABLE_CORNERS_PX = np.array([")
#         for i, (cx, cy) in enumerate(clicks):
#             print(f"    [{cx}, {cy}],   # {labels[i].lower()}")
#         print("], dtype=np.float32)")
#         print("─────────────────────────────────────────────────────")
#         plt.title("Done — 4 corners selected. Close the window.", fontsize=11)
#         fig.canvas.draw()
#
# fig.canvas.mpl_connect('button_press_event', on_click)
# plt.tight_layout()
# plt.show()

"""Building and Verifying Perspective Transform"""
# VIDEO_PATH = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV"
#
# #Paste corner output here
# TABLE_CORNERS_PX = np.array([
#     [1016, 1330],   # top-left
#     [2720, 1315],   # top-right
#     [3769, 1800],   # bottom-right
#     [3,    1834],   # bottom-left
# ], dtype=np.float32)
#
# #Real-world table dimensions
# #Standard ping pong table: 274cm x 152.5cm
# #Represented at 10 pixels per cm → 2740 x 1525 pixel canvas
# TABLE_W = 2740
# TABLE_H = 1525
#
# TABLE_CORNERS_REAL = np.array([
#     [0,       0      ],   # top-left
#     [TABLE_W, 0      ],   # top-right
#     [TABLE_W, TABLE_H],   # bottom-right
#     [0,       TABLE_H],   # bottom-left
# ], dtype=np.float32)
#
# #Compute transform matrix
# M = cv2.getPerspectiveTransform(TABLE_CORNERS_PX, TABLE_CORNERS_REAL)
# print("Transform matrix computed successfully")
# print(f"M =\n{M}\n")
#
# #Verification: Transform each corner and check it lands correctly
# print("── Corner verification ───────────────────────────────────────────────")
# labels   = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"]
# expected = [(0, 0), (TABLE_W, 0), (TABLE_W, TABLE_H), (0, TABLE_H)]
#
# all_correct = True
# for i, corner in enumerate(TABLE_CORNERS_PX):
#     pt     = np.array([[[corner[0], corner[1]]]], dtype=np.float32)
#     result = cv2.perspectiveTransform(pt, M)[0][0]
#     exp    = expected[i]
#     error  = abs(result[0] - exp[0]) + abs(result[1] - exp[1])
#     status = "✓" if error < 1.0 else "✗ CHECK THIS"
#     print(f"  {labels[i]}: pixel {corner.tolist()} → "
#           f"table ({result[0]:.1f}, {result[1]:.1f})  {status}")
#     if error >= 1.0:
#         all_correct = False
#
# print()
# if all_correct:
#     print("All corners map correctly — transform is good")
# else:
#     print("WARNING: Some corners are off — re-click them in Part 1")
#
# #Save M so you don't need to recompute it
# np.save("perspective_matrix.npy", M)
# print("Saved perspective_matrix.npy")
#
# #Warp first frame to bird's-eye view
# cap = cv2.VideoCapture(VIDEO_PATH)
# ret, frame = cap.read()
# cap.release()
#
# if not ret:
#     print("ERROR: Could not read video frame")
#     exit()
#
# warped      = cv2.warpPerspective(frame, M, (TABLE_W, TABLE_H))
# display     = cv2.resize(warped, (1096, 610))
# display_rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
#
# #Display with matplotlib
# plt.figure(figsize=(14, 8))
# plt.imshow(display_rgb)
# plt.title("Bird's-Eye View — verify table looks flat and rectangular",
#           fontsize=12)
# plt.axis('off')
# plt.tight_layout()
# plt.savefig("birdeye_check.jpg", dpi=150, bbox_inches='tight')
# plt.show()
# print("Saved birdeye_check.jpg")
#
# #Quick sanity check: test a midpoint
# mid_px = np.array([[[(TABLE_CORNERS_PX[0][0] + TABLE_CORNERS_PX[1][0]) / 2,
#                       (TABLE_CORNERS_PX[0][1] + TABLE_CORNERS_PX[2][1]) / 2]]],
#                   dtype=np.float32)
# mid_table = cv2.perspectiveTransform(mid_px, M)[0][0]
# print(f"\nSanity check — table center should be near "
#       f"({TABLE_W//2}, {TABLE_H//2}):")
# print(f"  Got: ({mid_table[0]:.1f}, {mid_table[1]:.1f})")

"""Apply transform to CSV"""
# #Load saved matrix and interpolated positions
# M  = np.load("perspective_matrix.npy")
# df = pd.read_csv("ball_positions_interpolated.csv")
#
# TABLE_W = 2740
# TABLE_H = 1525
#
# print(f"Loaded {len(df)} frames from interpolated CSV")
# print(f"Frames with ball position: {df['x'].notna().sum()}")
#
# #Convert each pixel position to table coordinates
# def pixel_to_table(row):
#     """Convert pixel (x, y) to table coordinate using perspective matrix."""
#     if pd.isna(row['x']) or pd.isna(row['y']):
#         return pd.Series({'table_x': None, 'table_y': None})
#
#     pt     = np.array([[[float(row['x']), float(row['y'])]]], dtype=np.float32)
#     result = cv2.perspectiveTransform(pt, M)[0][0]
#
#     tx, ty = float(result[0]), float(result[1])
#
#     # If the coordinate is way outside the table, the ball was off-table
#     # (rolling on floor, out of frame, etc.) — treat as no detection
#     if tx < -200 or tx > TABLE_W + 200 or ty < -200 or ty > TABLE_H + 200:
#         return pd.Series({'table_x': None, 'table_y': None})
#
#     return pd.Series({'table_x': tx, 'table_y': ty})
#
# # Apply to every row — this runs in a few seconds
# print("Applying perspective transform...")
# table_coords      = df.apply(pixel_to_table, axis=1)
# df['table_x']     = table_coords['table_x']
# df['table_y']     = table_coords['table_y']
#
# #Save final CSV
# df.to_csv("match_data.csv", index=False)
#
# #Summary
# total        = len(df)
# with_ball    = df['x'].notna().sum()
# on_table     = df['table_x'].notna().sum()
# off_table    = with_ball - on_table
#
# print(f"\n── match_data.csv summary ───────────────────────────────────────────")
# print(f"  Total frames:          {total}")
# print(f"  Frames with ball:      {with_ball}  ({100*with_ball/total:.1f}%)")
# print(f"  Ball on table:         {on_table}  ({100*on_table/total:.1f}%)")
# print(f"  Ball off table/floor:  {off_table}  ({100*off_table/total:.1f}%)")
# print(f"\nFirst 10 rows:")
# print(df[['frame', 'x', 'y', 'table_x', 'table_y']].head(10).to_string())
# print(f"\nSaved match_data.csv")

"""Initial Ball Heatmap"""
# TABLE_W = 2740
# TABLE_H = 1525
#
# #Load data
# df    = pd.read_csv("match_data.csv")
# valid = df.dropna(subset=['table_x', 'table_y'])
#
# # Clamp to table bounds — removes any remaining outliers
# valid = valid[
#     (valid['table_x'] >= 0) & (valid['table_x'] <= TABLE_W) &
#     (valid['table_y'] >= 0) & (valid['table_y'] <= TABLE_H)
# ].copy()
#
# print(f"Plotting {len(valid)} ball positions on heatmap")
#
# #Figure setup
# fig, axes = plt.subplots(1, 2, figsize=(18, 7))
# fig.patch.set_facecolor('#1a1a1a')
#
# def draw_table(ax):
#     ax.set_xlim(0, TABLE_W)
#     ax.set_ylim(0, TABLE_H)
#     ax.set_facecolor('#1a6b2e')
#     ax.set_aspect('equal')
#
#     # Table outline
#     ax.add_patch(patches.Rectangle(
#         (0, 0), TABLE_W, TABLE_H,
#         linewidth=3, edgecolor='white', facecolor='none'
#     ))
#
#     # Net — vertical line at midpoint of table length
#     ax.axvline(x=TABLE_W/2, color='white', linewidth=3)
#
#     # Center line along the length (dashed) — optional, standard on real tables
#     ax.axhline(y=TABLE_H/2, color='white', linewidth=1,
#                linestyle='--', alpha=0.4)
#
#     ax.tick_params(colors='white')
#     ax.set_xlabel("Table Length (cm × 10)", color='white', fontsize=10)
#     ax.set_ylabel("Table Width (cm × 10)",  color='white', fontsize=10)
#
# #Plot 1: Hexbin heatmap
# ax1 = axes[0]
# draw_table(ax1)
#
# hb = ax1.hexbin(
#     valid['table_x'], valid['table_y'],
#     gridsize=35, cmap='YlOrRd', alpha=0.85, mincnt=1
# )
# plt.colorbar(hb, ax=ax1, label='Ball frequency').ax.yaxis.label.set_color('white')
# ax1.set_title("Ball Placement Heatmap", color='white', fontsize=13, pad=12)
#
# # Label sides
# ax1.text(TABLE_W/2, TABLE_H*0.92, "Player 2 Side",
#          ha='center', color='white', fontsize=9, alpha=0.7)
# ax1.text(TABLE_W/2, TABLE_H*0.08, "Player 1 Side",
#          ha='center', color='white', fontsize=9, alpha=0.7)
#
# #Plot 2: Scatter with trajectory (first 500 detected frames)
# ax2 = axes[1]
# draw_table(ax2)
#
# # Trajectory line — connect consecutive detections
# traj = valid.head(500)
# ax2.plot(traj['table_x'], traj['table_y'],
#          color='yellow', alpha=0.2, linewidth=0.8, zorder=1)
# ax2.scatter(traj['table_x'], traj['table_y'],
#             c='yellow', s=8, alpha=0.5, zorder=2)
#
# ax2.set_title("Ball Trajectory (first 500 detections)",
#               color='white', fontsize=13, pad=12)
#
# plt.tight_layout(pad=2.0)
# plt.savefig("ball_heatmap.png", dpi=150,
#             bbox_inches='tight', facecolor='#1a1a1a')
# print("Saved ball_heatmap.png")
# plt.show()

"""Tracker Verification"""
# VIDEO_PATH  = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV"
# MAX_FRAMES  = 300    # only check first 300 frames (~10 sec) for verification
#
# #Models + Tracker
# player_model = YOLO("yolov8n.pt")      # pretrained COCO — no training needed
# tracker      = sv.ByteTrack()
#
# cap       = cv2.VideoCapture(VIDEO_PATH)
# fps       = cap.get(cv2.CAP_PROP_FPS)
# w         = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
# h         = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
# frame_num = 0
# frames_out = []
#
# print(f"Video: {w}x{h} @ {fps:.1f}fps")
# print("Running player tracker on first 300 frames...")
#
# while cap.isOpened() and frame_num < MAX_FRAMES:
#     ret, frame = cap.read()
#     if not ret:
#         break
#
#     # Detect persons only (class 0), ignore everything else
#     results    = player_model(frame, classes=[0], conf=0.5, imgsz=1280)[0]
#     detections = sv.Detections.from_ultralytics(results)
#     detections = tracker.update_with_detections(detections)
#
#     # Draw bounding boxes + IDs manually (avoid cv2.imshow)
#     annotated = frame.copy()
#     for i, box in enumerate(detections.xyxy):
#         x1, y1, x2, y2 = map(int, box)
#         tid  = int(detections.tracker_id[i]) if detections.tracker_id is not None else -1
#         conf = float(detections.confidence[i])
#
#         color = (255, 100, 0) if tid == 1 else (0, 180, 255)   # P1=orange, P2=blue
#         cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
#         cv2.putText(annotated, f"P{tid} ({conf:.2f})",
#                     (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
#                     0.7, color, 2)
#
#     frames_out.append(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
#     frame_num += 1
#
# cap.release()
#
# #Show sample frames using matplotlib
# print(f"Processed {frame_num} frames. Showing sample frames...")
# sample_indices = [0, 50, 100, 200, 299]
# fig, axes = plt.subplots(1, len(sample_indices), figsize=(20, 5))
#
# for ax, idx in zip(axes, sample_indices):
#     if idx < len(frames_out):
#         ax.imshow(frames_out[idx])
#         ax.set_title(f"Frame {idx}", fontsize=9)
#         ax.axis('off')
#
# plt.suptitle("Player Tracking Verification — IDs should stay consistent",
#              fontsize=12)
# plt.tight_layout()
# plt.savefig("player_tracking_check.png", dpi=120, bbox_inches='tight')
# plt.show()
# print("Saved player_tracking_check.png")

"""Ball + Player Tracker"""
# VIDEO_PATH   = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV"
# BALL_MODEL   = r"runs\detect\pingpong_ball_v1-2\weights\best.pt"
# RAW_CSV      = r"raw_detections.csv"
#
# #Models + Tracker
# ball_model   = YOLO(BALL_MODEL)
# player_model = YOLO("yolov8n.pt")
# tracker = sv.ByteTrack(
#     track_activation_threshold=0.25,
#     lost_track_buffer=90,      # hold lost tracks for 90 frames (~3 sec at 30fps)
#     minimum_matching_threshold=0.8,
#     frame_rate=30
# )
#
# cap       = cv2.VideoCapture(VIDEO_PATH)
# fps       = cap.get(cv2.CAP_PROP_FPS)
# total     = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
# frame_num = 0
#
# print(f"Processing {total} frames (~{total/fps/60:.1f} min of footage)")
# print(f"Estimated time: ~40-50 minutes on CPU")
# print(f"Saving to: {RAW_CSV}\n")
#
# #Write directly to CSV per frame
# with open(RAW_CSV, 'w', newline='') as f:
#     writer = csv.writer(f)
#     writer.writerow([
#         'frame', 'type', 'track_id',
#         'pixel_x', 'pixel_y',
#         'x1', 'y1', 'x2', 'y2',
#         'confidence'
#     ])
#
#     while cap.isOpened():
#         ret, frame = cap.read()
#         if not ret:
#             break
#
#         #Ball detection
#         ball_results = ball_model(frame, conf=0.3, imgsz=1280)[0]
#         ball_found   = False
#
#         for i, cls in enumerate(ball_results.boxes.cls):
#             if int(cls) == 0:
#                 x1, y1, x2, y2 = ball_results.boxes.xyxy[i].tolist()
#                 cx   = (x1 + x2) / 2
#                 cy   = (y1 + y2) / 2
#                 conf = float(ball_results.boxes.conf[i])
#                 writer.writerow([
#                     frame_num, 'ball', None,
#                     cx, cy, x1, y1, x2, y2, conf
#                 ])
#                 ball_found = True
#                 break   # only take highest-confidence ball detection
#
#         # Always write a row for the ball — None if not detected
#         if not ball_found:
#             writer.writerow([
#                 frame_num, 'ball', None,
#                 None, None, None, None, None, None, None
#             ])
#
#         #Player detection + tracking
#         player_results = player_model(frame, classes=[0], conf=0.5, imgsz=1280)[0]
#         detections     = sv.Detections.from_ultralytics(player_results)
#         detections     = tracker.update_with_detections(detections)
#
#         for i, box in enumerate(detections.xyxy):
#             x1, y1, x2, y2 = box.tolist()
#             cx   = (x1 + x2) / 2
#             cy   = (y1 + y2) / 2
#             tid  = int(detections.tracker_id[i]) if detections.tracker_id is not None else -1
#             conf = float(detections.confidence[i])
#             writer.writerow([
#                 frame_num, 'player', tid,
#                 cx, cy, x1, y1, x2, y2, conf
#             ])
#
#         frame_num += 1
#
#         # Progress update every 500 frames
#         if frame_num % 500 == 0:
#             pct = 100 * frame_num / total
#             print(f"  [{frame_num}/{total}] {pct:.1f}% complete")
#
# cap.release()
# print(f"\nDone — {frame_num} frames processed")
# print(f"Saved to {RAW_CSV}")

"""Interpolation + Transformation"""
# RAW_CSV   = r"raw_detections.csv"
# FINAL_CSV = r"match_data.csv"
# M         = np.load("perspective_matrix.npy")
#
# TABLE_W = 2740
# TABLE_H = 1525
#
# # ── Load raw detections ────────────────────────────────────────────────────
# df = pd.read_csv(RAW_CSV)
# df['pixel_x']    = pd.to_numeric(df['pixel_x'],    errors='coerce')
# df['pixel_y']    = pd.to_numeric(df['pixel_y'],    errors='coerce')
# df['confidence'] = pd.to_numeric(df['confidence'], errors='coerce')
#
# print(f"Loaded {len(df)} rows from raw detections")
# print(f"  Ball rows:   {len(df[df['type']=='ball'])}")
# print(f"  Player rows: {len(df[df['type']=='player'])}")
#
# # ── Interpolate ball positions (limit=10 frames) ───────────────────────────
# print("\nInterpolating ball positions...")
# ball_df = df[df['type'] == 'ball'].copy().sort_values('frame')
# ball_df['pixel_x'] = ball_df['pixel_x'].interpolate(method='linear', limit=10)
# ball_df['pixel_y'] = ball_df['pixel_y'].interpolate(method='linear', limit=10)
#
# # ── Perspective transform function ────────────────────────────────────────
# def to_table_coords(px, py):
#     """Convert pixel (x, y) to table coordinates. Returns (None, None) if off-table."""
#     if pd.isna(px) or pd.isna(py):
#         return None, None
#
#     pt     = np.array([[[float(px), float(py)]]], dtype=np.float32)
#     result = cv2.perspectiveTransform(pt, M)[0][0]
#     tx, ty = float(result[0]), float(result[1])
#
#     # Filter positions far outside the table
#     if tx < -400 or tx > TABLE_W + 400 or ty < -400 or ty > TABLE_H + 400:
#         return None, None
#
#     return tx, ty
#
# # ── Apply transform to ball positions ─────────────────────────────────────
# print("Applying perspective transform to ball positions...")
# ball_table = ball_df.apply(
#     lambda r: pd.Series(to_table_coords(r['pixel_x'], r['pixel_y'])),
#     axis=1
# )
# ball_df['table_x'] = ball_table[0]
# ball_df['table_y'] = ball_table[1]
#
# # ── Apply transform to player positions ───────────────────────────────────
# print("Applying perspective transform to player positions...")
# player_df = df[df['type'] == 'player'].copy()
# player_table = player_df.apply(
#     lambda r: pd.Series(to_table_coords(r['pixel_x'], r['pixel_y'])),
#     axis=1
# )
# player_df['table_x'] = player_table[0]
# player_df['table_y'] = player_table[1]
#
# # ── Merge back together ────────────────────────────────────────────────────
# final_df = pd.concat([ball_df, player_df]).sort_values(
#     ['frame', 'type']
# ).reset_index(drop=True)
#
# final_df.to_csv(FINAL_CSV, index=False)
#
# # ── Summary ────────────────────────────────────────────────────────────────
# ball_rows   = final_df[final_df['type'] == 'ball']
# player_rows = final_df[final_df['type'] == 'player']
#
# print(f"\n── match_data.csv summary ───────────────────────────────────────────")
# print(f"  Total rows:              {len(final_df)}")
# print(f"  Ball frames (total):     {len(ball_rows)}")
# print(f"  Ball on table:           {ball_rows['table_x'].notna().sum()}")
# print(f"  Player detections:       {len(player_rows)}")
# print(f"  Unique player IDs:       {player_rows['track_id'].nunique()}")
#
# # Show player IDs detected
# ids = sorted(player_rows['track_id'].dropna().unique().astype(int))
# print(f"  Player IDs:              {ids}")
# print(f"\nSaved {FINAL_CSV}")

"""Checking for 2 Player ID's - Cleanup CSV"""
# FINAL_CSV = r"match_data.csv"
#
# df       = pd.read_csv(FINAL_CSV)
# player_df = df[df['type'] == 'player'].copy()
#
# #Get average pixel_x position per track ID
# # Players occupy opposite horizontal halves of the frame
# # so mean pixel_x cleanly separates them
# id_positions = (
#     player_df.groupby('track_id')['pixel_x']
#     .mean()
#     .dropna()
#     .reset_index()
# )
# id_positions.columns = ['track_id', 'mean_x']
#
# print(f"Clustering {len(id_positions)} track IDs into 2 players...")
#
# #K-means with k=2
# kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
# id_positions['cluster'] = kmeans.fit_predict(id_positions[['mean_x']])
#
# # Assign Player 1 to left side (lower mean_x), Player 2 to right side
# centers = kmeans.cluster_centers_.flatten()
# left_cluster  = int(np.argmin(centers))    # smaller x = left side = Player 1
# right_cluster = int(np.argmax(centers))    # larger x  = right side = Player 2
#
# id_positions['real_player_id'] = id_positions['cluster'].apply(
#     lambda c: 1 if c == left_cluster else 2
# )
#
# #Show the mapping
# print("\nCluster centers (mean pixel_x):")
# print(f"  Player 1 side: x = {centers[left_cluster]:.0f}px")
# print(f"  Player 2 side: x = {centers[right_cluster]:.0f}px")
#
# p1_ids = id_positions[id_positions['real_player_id'] == 1]['track_id'].tolist()
# p2_ids = id_positions[id_positions['real_player_id'] == 2]['track_id'].tolist()
# print(f"\n  {len(p1_ids)} track IDs → Player 1")
# print(f"  {len(p2_ids)} track IDs → Player 2")
#
# #Build mapping dict and apply to dataframe
# id_map = dict(zip(id_positions['track_id'], id_positions['real_player_id']))
# player_df['track_id'] = player_df['track_id'].map(id_map)
#
# #Merge back with ball rows and save
# ball_df  = df[df['type'] == 'ball'].copy()
# final_df = pd.concat([ball_df, player_df]).sort_values(
#     ['frame', 'type']
# ).reset_index(drop=True)
#
# final_df.to_csv(FINAL_CSV, index=False)
#
# #Verify
# player_check = final_df[final_df['type'] == 'player']
# print(f"\n── After cleanup ─────────────────────────────────────────────────────")
# print(f"  Unique player IDs: {sorted(player_check['track_id'].dropna().unique().astype(int))}")
# print(f"  Player 1 detections: {len(player_check[player_check['track_id'] == 1])}")
# print(f"  Player 2 detections: {len(player_check[player_check['track_id'] == 2])}")
# print(f"\nSaved cleaned {FINAL_CSV}")

"""Annotated Video"""
# VIDEO_PATH    = r"C:\Users\rudra\Downloads\Projects\Ping Pong Performance App\Videos\OrangeBall1.MOV"
# FINAL_CSV     = r"match_data.csv"
# OUTPUT_VIDEO  = r"output_annotated.mp4"
#
# #Load data
# df = pd.read_csv(FINAL_CSV)
#
# #Pre-index by frame number for fast lookup
# ball_by_frame   = {}
# player_by_frame = {}
#
# for frame_num, group in df.groupby('frame'):
#     ball_rows   = group[group['type'] == 'ball']
#     player_rows = group[group['type'] == 'player']
#
#     if not ball_rows.empty:
#         row = ball_rows.iloc[0]
#         if pd.notna(row['pixel_x']):
#             ball_by_frame[frame_num] = (int(row['pixel_x']), int(row['pixel_y']))
#
#     players = {}
#     for _, row in player_rows.iterrows():
#         if pd.notna(row['pixel_x']) and pd.notna(row['track_id']):
#             players[int(row['track_id'])] = {
#                 'center': (int(row['pixel_x']), int(row['pixel_y'])),
#                 'box':    (int(row['x1']), int(row['y1']),
#                            int(row['x2']), int(row['y2']))
#             }
#     if players:
#         player_by_frame[frame_num] = players
#
# #Video writer
# cap     = cv2.VideoCapture(VIDEO_PATH)
# fps     = cap.get(cv2.CAP_PROP_FPS)
# w       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
# h       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
# total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
# writer  = cv2.VideoWriter(
#     OUTPUT_VIDEO,
#     cv2.VideoWriter_fourcc(*'mp4v'),
#     fps, (w, h)
# )
#
# print(f"Rendering annotated video: {total} frames")
#
# frame_num  = 0
# ball_trail = []      # rolling window of last 20 ball positions
#
# while cap.isOpened():
#     ret, frame = cap.read()
#     if not ret:
#         break
#
#     #Ball trail
#     ball_pos = ball_by_frame.get(frame_num)
#     ball_trail.append(ball_pos)
#     ball_trail = ball_trail[-20:]    # keep last 20 positions
#
#     # Draw trail (fading opacity)
#     for i in range(1, len(ball_trail)):
#         if ball_trail[i-1] and ball_trail[i]:
#             alpha    = i / len(ball_trail)
#             color    = (0, int(255 * alpha), int(255 * alpha))
#             thickness = max(1, int(3 * alpha))
#             cv2.line(frame, ball_trail[i-1], ball_trail[i], color, thickness)
#
#     # Draw current ball position
#     if ball_pos:
#         cv2.circle(frame, ball_pos, 8, (0, 255, 255), -1)
#         cv2.circle(frame, ball_pos, 10, (0, 180, 180), 2)
#
#     #Players
#     players = player_by_frame.get(frame_num, {})
#     colors  = {1: (255, 100, 0), 2: (0, 180, 255)}   # P1=orange, P2=blue
#
#     for tid, data in players.items():
#         color  = colors.get(tid, (200, 200, 200))
#         x1, y1, x2, y2 = data['box']
#         cx, cy          = data['center']
#
#         cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
#         cv2.putText(frame, f"Player {tid}",
#                     (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
#                     0.8, color, 2)
#
#         # Dot at player center (feet position — more accurate for table coords)
#         cv2.circle(frame, (cx, cy), 5, color, -1)
#
#     #Frame counter
#     cv2.putText(frame, f"Frame {frame_num}",
#                 (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
#                 1.0, (255, 255, 255), 2)
#
#     writer.write(frame)
#     frame_num += 1
#
#     if frame_num % 500 == 0:
#         print(f"  Rendered {frame_num}/{total} frames")
#
# cap.release()
# writer.release()
# print(f"\nSaved {OUTPUT_VIDEO}")

"""Final Heatmap"""
# FINAL_CSV = r"match_data.csv"
# TABLE_W   = 2740
# TABLE_H   = 1525
#
# df = pd.read_csv(FINAL_CSV)
# ball  = df[df['type'] == 'ball'].dropna(subset=['table_x', 'table_y'])
# ball  = ball[
#     (ball['table_x'] >= 0) & (ball['table_x'] <= TABLE_W) &
#     (ball['table_y'] >= 0) & (ball['table_y'] <= TABLE_H)
# ].copy()
#
# # Split by table half — net is at table_x = TABLE_W/2
# p1_side = ball[ball['table_x'] <= TABLE_W / 2]   # Player 1's side
# p2_side = ball[ball['table_x'] >  TABLE_W / 2]   # Player 2's side
#
# print(f"Ball positions on P1 side: {len(p1_side)}")
# print(f"Ball positions on P2 side: {len(p2_side)}")
#
# #Draw table helper
# def draw_table(ax, title):
#     ax.set_xlim(0, TABLE_W)
#     ax.set_ylim(0, TABLE_H)
#     ax.set_facecolor('#1a6b2e')
#     ax.set_aspect('equal')
#     ax.add_patch(patches.Rectangle(
#         (0, 0), TABLE_W, TABLE_H,
#         linewidth=3, edgecolor='white', facecolor='none'
#     ))
#     ax.axvline(x=TABLE_W/2, color='white', linewidth=3)         # net
#     ax.axhline(y=TABLE_H/2, color='white', linewidth=1,
#                linestyle='--', alpha=0.4)                        # center line
#     ax.set_title(title, color='white', fontsize=12, pad=10)
#     ax.tick_params(colors='white')
#
# #Figure
# fig, axes = plt.subplots(1, 3, figsize=(22, 7))
# fig.patch.set_facecolor('#1a1a1a')
#
# # Plot 1: Full heatmap
# draw_table(axes[0], "Full Match — Ball Placement")
# hb = axes[0].hexbin(ball['table_x'], ball['table_y'],
#                     gridsize=30, cmap='YlOrRd', alpha=0.85, mincnt=1)
# plt.colorbar(hb, ax=axes[0]).ax.yaxis.label.set_color('white')
# axes[0].text(TABLE_W*0.25, TABLE_H*0.95, "Player 1",
#              ha='center', color='white', fontsize=9, alpha=0.8)
# axes[0].text(TABLE_W*0.75, TABLE_H*0.95, "Player 2",
#              ha='center', color='white', fontsize=9, alpha=0.8)
#
# # Plot 2: Player 1's side (where P2 lands shots)
# draw_table(axes[1], "Player 1's Side\n(P2's shot placement)")
# if len(p1_side) > 0:
#     axes[1].hexbin(p1_side['table_x'], p1_side['table_y'],
#                    gridsize=20, cmap='Blues', alpha=0.85, mincnt=1)
# axes[1].text(TABLE_W*0.25, TABLE_H*0.5, f"{len(p1_side)} shots",
#              ha='center', va='center', color='white', fontsize=10)
#
# # Plot 3: Player 2's side (where P1 lands shots)
# draw_table(axes[2], "Player 2's Side\n(P1's shot placement)")
# if len(p2_side) > 0:
#     axes[2].hexbin(p2_side['table_x'], p2_side['table_y'],
#                    gridsize=20, cmap='Oranges', alpha=0.85, mincnt=1)
# axes[2].text(TABLE_W*0.75, TABLE_H*0.5, f"{len(p2_side)} shots",
#              ha='center', va='center', color='white', fontsize=10)
#
# plt.suptitle("Ping Pong Match Analysis", color='white',
#              fontsize=15, fontweight='bold', y=1.02)
# plt.tight_layout(pad=2.0)
# plt.savefig("final_heatmap.png", dpi=150,
#             bbox_inches='tight', facecolor='#1a1a1a')
# plt.show()
# print("Saved final_heatmap.png")