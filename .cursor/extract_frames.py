import cv2
from pathlib import Path

src = Path(r'c:\Users\GY\Videos\Записи экрана\Запись экрана 2026-11-11 211446.mp4')
out_dir = Path(r'C:\Users\GY\WebstormProjects\gin\.cursor\screen-rec-frames')
out_dir.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(str(src))
if not cap.isOpened():
    raise SystemExit(f'cannot open {src}')

fps = cap.get(cv2.CAP_PROP_FPS) or 30
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
dur = n / fps if fps else 0
print(f'fps={fps:.2f} frames={n} duration={dur:.2f}s')

targets = []
if n <= 1:
    targets = [0]
else:
    steps = min(8, max(1, n))
    for i in range(steps):
        targets.append(int(i * (n - 1) / max(1, steps - 1)))

saved = []
for idx, fno in enumerate(targets):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
    ok, frame = cap.read()
    if not ok:
        continue
    path = out_dir / f'frame_{idx:02d}_{fno}.jpg'
    h, w = frame.shape[:2]
    scale = min(1.0, 1280 / w)
    if scale < 1:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    saved.append(path)
    print('saved', path.name, 'at frame', fno)

cap.release()
print('done', len(saved))
