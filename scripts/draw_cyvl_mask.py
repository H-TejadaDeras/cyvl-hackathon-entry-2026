import os
from PIL import Image, ImageDraw
import numpy as np

def draw_real_cyvl_mask():
    src_path = "/Users/kilpy/cyvl-hackathon-entry-2026/scripts/cyvl_real_image.jpg"
    dst_path = "/Users/kilpy/cyvl-hackathon-entry-2026/scripts/segmented_cyvl.png"
    
    img = Image.open(src_path).convert("RGBA")
    width, height = img.size
    
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Simulate a network of cracks in the middle of the road (lower center)
    cx, cy = width // 2, int(height * 0.75)
    
    np.random.seed(123)
    # Draw a branching structure
    for _ in range(8):
        points = []
        curr_x, curr_y = cx, cy
        points.append((curr_x, curr_y))
        for _ in range(np.random.randint(4, 8)):
            curr_x += np.random.randint(-100, 100)
            curr_y += np.random.randint(-150, 50)
            points.append((curr_x, curr_y))
        
        # Draw the line segment
        draw.line(points, fill=(255, 0, 0, 150), width=8)
        
        # Draw some localized polygon blobs to simulate severe localized cracking (alligator)
        for i in range(len(points) - 1):
            if np.random.random() > 0.6:
                px, py = points[i]
                rad = np.random.randint(20, 60)
                poly = [
                    (px + np.random.randint(-rad, rad), py + np.random.randint(-rad, rad))
                    for _ in range(6)
                ]
                draw.polygon(poly, fill=(255, 50, 0, 80), outline=(255, 0, 0, 150), width=3)
                
    result = Image.alpha_composite(img, overlay)
    result = result.convert("RGB")
    result.save(dst_path)
    print(f"Saved {dst_path}")

if __name__ == "__main__":
    draw_real_cyvl_mask()
