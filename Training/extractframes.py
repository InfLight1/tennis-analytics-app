import os
import cv2

cap = cv2.VideoCapture(r"/Videos/Tennis1.mp4")
os.makedirs("frames", exist_ok=True)
frame_count = 0
saved = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    if frame_count % 15 == 0:           # every 15th frame
        cv2.imwrite(f"frames/frame_{saved:04d}.jpg", frame)
        saved += 1
    frame_count += 1

cap.release()
print(f"Extracted {saved} frames")