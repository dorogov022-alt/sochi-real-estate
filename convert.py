from PIL import Image
import os

folder = "static/images"

for file in os.listdir(folder):
    if file.endswith(".jpg") or file.endswith(".png"):
        img = Image.open(os.path.join(folder, file))
        name = os.path.splitext(file)[0]
        img.save(os.path.join(folder, name + ".webp"), "webp", quality=80)
