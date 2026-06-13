import cv2
import numpy as np
import os
from ultralytics import SAM

def run_vision_pipeline(img_path, out_path):
    print(f"Starting SAM2 Pipeline for {img_path}...")
    
    img = cv2.imread(img_path)
    if img is None:
        print("Image not found!")
        return False
        
    h, w = img.shape[:2]
    
    # 1. Segment Road using SAM2 (Latest Segment Anything Model)
    # We use SAM2 with a point prompt at the bottom-center of the image where the road is guaranteed to be.
    print("Running SAM2 for precise Road Segmentation...")
    model = SAM('sam2_s.pt') # Using SAM2 Small for speed while maintaining high accuracy
    
    # Prompt the center of the image, slightly below the horizon (the ego-vehicle's lane)
    # Avoiding the bottom 20% because that is the car's dashboard/hood reflection!
    road_point = [[int(w / 2), int(h * 0.65)]]
    
    # Predict with point prompt
    results = model(img, points=road_point, labels=[1], device='cpu', retina_masks=True)
    
    road_mask = np.zeros((h, w), dtype=np.uint8)
    if results[0].masks is not None:
        # Extract the mask and convert to uint8 before resizing
        mask_data = results[0].masks.data.cpu().numpy()[0]
        mask_data = mask_data.astype(np.uint8)
        road_mask = cv2.resize(mask_data, (w, h), interpolation=cv2.INTER_NEAREST)
        road_mask = (road_mask * 255).astype(np.uint8)
    else:
        print("SAM2 failed to find a mask. Falling back to heuristic.")
        road_mask[int(h*0.6):, :] = 255
        
    # Instead of a harsh crop that cuts out parts of the road, we will darken the background
    # and keep the full road polygon brightly illuminated.
    background_darkened = cv2.addWeighted(img, 0.3, np.zeros_like(img), 0.7, 0)
    
    # Combine the bright road with the darkened background
    road_only = cv2.bitwise_and(img, img, mask=road_mask)
    bg_only = cv2.bitwise_and(background_darkened, background_darkened, mask=cv2.bitwise_not(road_mask))
    focused_img = cv2.add(road_only, bg_only)
        
    # 2. Find Cracks using Edge Detection strictly inside the SAM2 Road Mask
    print("Running Crack Segmentation on SAM2 Road Surface...")
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5)
    
    # Restrict strictly to the SAM2 polygon mask
    thresh = cv2.bitwise_and(thresh, thresh, mask=road_mask)
    
    kernel = np.ones((3,3), np.uint8)
    cracks = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # 3. Draw the SAM/Crack Polygons over the original image
    overlay = img.copy()
    crack_contours, _ = cv2.findContours(cracks, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    num_cracks = 0
    for cnt in crack_contours:
        area = cv2.contourArea(cnt)
        if 50 < area < 5000:
            num_cracks += 1
            cv2.drawContours(overlay, [cnt], -1, (0, 0, 255), -1)
            cv2.drawContours(overlay, [cnt], -1, (0, 255, 255), 1)
            
    alpha = 0.6
    final_img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
    
    # We will crop the image to remove the extreme top sky/trees and the bottom car hood
    # Find bounding box of the road mask
    contours, _ = cv2.findContours(road_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        c = max(contours, key=cv2.contourArea)
        rx, ry, rw, rh = cv2.boundingRect(c)
        ry = max(0, ry - 50) # Give 50px padding above the road horizon
        
        # Crop the final image to remove sky/trees (everything above ry)
        # And remove the bottom 15% (which is the car hood)
        bottom_crop = int(h * 0.85)
        final_img = final_img[ry:bottom_crop, 0:w]
    
    cv2.imwrite(out_path, final_img)
    print(f"Saved output to {out_path} with {num_cracks} cracks found.")
    return num_cracks

if __name__ == '__main__':
    cracks = run_vision_pipeline('/Users/kilpy/cyvl-hackathon-entry-2026/scripts/cyvl_real_image.jpg', '/Users/kilpy/cyvl-hackathon-entry-2026/scripts/segmented_cyvl.png')
    print(f"Test found {cracks} cracks")
