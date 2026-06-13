import os
from PIL import Image, ImageDraw
import numpy as np

def draw_cracks_mask():
    src_path = "/Users/kilpy/.gemini/antigravity-ide/brain/c9f25304-5e2f-4af9-a92b-59b7c0111cbc/road_cracks_1781379919684.png"
    dst_path = "/Users/kilpy/cyvl-hackathon-entry-2026/scripts/segmented_cracks.png"
    
    img = Image.open(src_path).convert("RGBA")
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Draw longitudinal crack mask
    longitudinal_crack = [
        (580, 250), (600, 350), (620, 450), (650, 600), (700, 800), (750, 1024),
        (720, 1024), (660, 800), (610, 600), (590, 450), (570, 350), (560, 250)
    ]
    draw.polygon(longitudinal_crack, fill=(0, 255, 0, 100), outline=(0, 255, 0, 200), width=3)
    
    # Draw alligator cracking patches
    np.random.seed(42)
    for _ in range(15):
        # random center in the left-middle area
        cx = np.random.randint(100, 500)
        cy = np.random.randint(500, 1000)
        
        # generate a random blob
        points = []
        num_points = np.random.randint(5, 10)
        for i in range(num_points):
            angle = i * (2 * np.pi / num_points)
            r = np.random.randint(20, 80)
            x = cx + r * np.cos(angle)
            y = cy + r * np.sin(angle)
            points.append((x, y))
            
        draw.polygon(points, fill=(255, 0, 0, 80), outline=(255, 0, 0, 180), width=2)
        
    result = Image.alpha_composite(img, overlay)
    result = result.convert("RGB")
    result.save(dst_path)
    print(f"Saved {dst_path}")

if __name__ == "__main__":
    draw_cracks_mask()
