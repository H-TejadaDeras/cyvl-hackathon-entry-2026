from flask import Flask, jsonify, request, render_template, send_from_directory
import geopandas as gpd
import os
import urllib.request
import uuid
from run_ai_vision import run_vision_pipeline
from generate_dxf import generate_dxf_model
from aps_utils import upload_dxf_and_translate, get_public_token
from shapely.geometry import Point

app = Flask(__name__)

# Load image dataset once
print("Loading Cyvl Image Index...")
img_df = gpd.read_file('../data/CityofSomervilleMAMarketingDemo-plainImagery/layer_zip.shp')
img_df = img_df.to_crs("EPSG:4326")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/api/process_segment', methods=['POST'])
def process_segment():
    data = request.json
    lat = data.get('lat')
    lon = data.get('lon')
    score = data.get('score', 50)
    
    print(f"Received request for lat={lat}, lon={lon}, score={score}")
    
    # 1. Find nearest image
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    distances = img_df.geometry.distance(pt[0])
    nearest_idx = distances.idxmin()
    img_row = img_df.loc[nearest_idx]
    image_url = img_row['image_url']
    
    # 2. Download Image
    img_id = str(uuid.uuid4())
    src_path = os.path.join('static', 'images', f'{img_id}_raw.jpg')
    out_path = os.path.join('static', 'images', f'{img_id}_segmented.png')
    
    print(f"Downloading nearest image: {image_url}")
    urllib.request.urlretrieve(image_url, src_path)
    
    # 3. Run Pipeline
    print(f"Running AI Vision Pipeline...")
    num_cracks = run_vision_pipeline(src_path, out_path)
    if num_cracks is False:
        return jsonify({"error": "Failed to process image"}), 500
        
    # 4. Generate Autodesk DXF CAD Model
    dxf_filename = f"{img_id}_model.dxf"
    dxf_path = os.path.join('static', 'models', dxf_filename)
    
    # Ensure directory exists
    os.makedirs(os.path.join('static', 'models'), exist_ok=True)
    
    success, vol, obj_path = generate_dxf_model(lat=lat, lon=lon, num_cracks=num_cracks, output_path=dxf_path)
    if not success:
        return jsonify({"error": "Failed to generate DXF"}), 500
    
    # 5. Upload to Autodesk Platform Services
    urn = upload_dxf_and_translate(dxf_path, dxf_filename)
    
    return jsonify({
        "image_url": f"/{out_path}",
        "dxf_url": f"/{dxf_path}",
        "obj_url": f"/{obj_path}",
        "urn": urn,
        "volume": vol
    })

@app.route('/api/aps_token', methods=['GET'])
def aps_token():
    token_data = get_public_token()
    if token_data:
        return jsonify(token_data)
    return jsonify({"error": "Failed to get APS token"}), 500

@app.route('/api/open_cad', methods=['POST'])
def open_cad():
    data = request.json
    dxf_url = data.get('dxf_url')
    if dxf_url:
        local_path = dxf_url.lstrip('/')
        if os.path.exists(local_path):
            os.system(f'open "{local_path}"')
            return jsonify({"status": "opened"})
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(port=8000, debug=True)
