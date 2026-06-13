import os
from PIL import Image, ImageDraw

def draw_sam_mask():
    src_path = "/Users/kilpy/.gemini/antigravity-ide/brain/c9f25304-5e2f-4af9-a92b-59b7c0111cbc/road_view_1781379744230.png"
    dst_path = "/Users/kilpy/cyvl-hackathon-entry-2026/scripts/segmented_road.png"
    
    img = Image.open(src_path).convert("RGBA")
    
    # Create an overlay for the mask
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Polygon coordinates around the center pothole in the 1024x1024 image
    # The pothole is roughly from y=600 to y=800, x=300 to x=700
    polygon = [
        (320, 680),
        (380, 620),
        (500, 580),
        (620, 600),
        (680, 650),
        (650, 720),
        (580, 760),
        (450, 750),
        (350, 720)
    ]
    
    # Draw a semi-transparent red mask (SAM style)
    draw.polygon(polygon, fill=(255, 0, 0, 100), outline=(255, 0, 0, 255), width=3)
    
    # Composite the overlay onto the image
    result = Image.alpha_composite(img, overlay)
    result = result.convert("RGB")
    result.save(dst_path)
    print(f"Saved {dst_path}")

if __name__ == "__main__":
    draw_sam_mask()
