import os
import numpy as np
from PIL import Image

SRC = r"E:\DSH-Data\home\attachments\v1\objects\2a\2a692731a31d1e582ab8dc7dfe9774080f249a23bbca6fd9ae22471a3b63e2bd"
WORK = r"E:\图号助手\图片编辑"
a = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
gray = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)

for x in (30, 70, 100, 130, 145):
    prof = [int(gray[y, x]) for y in range(88, 160, 2)]
    print(f"x={x}:", prof)
print()
for y in (105, 118, 130, 142, 152):
    prof = [int(gray[y, x]) for x in range(12, 160, 4)]
    print(f"y={y}:", prof)
