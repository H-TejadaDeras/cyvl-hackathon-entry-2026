import os
import numpy as np
import ezdxf
from pyproj import Transformer
from scipy.spatial import Delaunay

LIDAR_FILE = '/Users/kilpy/cyvl-hackathon-entry-2026/data/processed/ground_points.npy'
if os.path.exists(LIDAR_FILE):
    lidar_data = np.load(LIDAR_FILE)
else:
    lidar_data = None

transformer = Transformer.from_crs("EPSG:4326", "EPSG:26919", always_xy=True)

def generate_dxf_model(lat, lon, num_cracks, output_path):
    easting, northing = transformer.transform(lon, lat)
    
    local_pts = []
    if lidar_data is not None:
        mask = (np.abs(lidar_data[:, 0] - easting) < 15) & (np.abs(lidar_data[:, 1] - northing) < 15)
        local_pts = lidar_data[mask]
    
    if len(local_pts) == 0:
        # Fallback: Simulate flat road surface if no LiDAR points are found in this area
        x = np.random.uniform(easting - 15, easting + 15, 2000)
        y = np.random.uniform(northing - 15, northing + 15, 2000)
        z = np.full(2000, 5.0)
        local_pts = np.column_stack((x, y, z))
        
    if len(local_pts) > 2000:
        indices = np.random.choice(len(local_pts), 2000, replace=False)
        local_pts = local_pts[indices]
        
    z_min = np.min(local_pts[:, 2])
    shifted_pts = local_pts.copy()
    shifted_pts[:, 0] -= easting
    shifted_pts[:, 1] -= northing
    shifted_pts[:, 2] -= z_min
    
    # Volume calculation simulation (using dummy values proportional to cracks for demo purposes)
    # Real volumetric calculation requires full depression matching which is heavy.
    vol = num_cracks * 0.45 + np.random.uniform(0.1, 0.5)
    
    doc = ezdxf.new('R2010')
    doc.layers.add("STREET_MESH", color=ezdxf.colors.WHITE)
    doc.layers.add("WATER_LINE", color=ezdxf.colors.BLUE)
    doc.layers.add("CRACKS", color=ezdxf.colors.RED)
    
    msp = doc.modelspace()
    
    xy = shifted_pts[:, :2]
    try:
        tri = Delaunay(xy)
        for simplex in tri.simplices:
            p1 = shifted_pts[simplex[0]]
            p2 = shifted_pts[simplex[1]]
            p3 = shifted_pts[simplex[2]]
            
            msp.add_3dface([
                (p1[0], p1[1], p1[2]),
                (p2[0], p2[1], p2[2]),
                (p3[0], p3[1], p3[2]),
                (p3[0], p3[1], p3[2])
            ], dxfattribs={'layer': 'STREET_MESH'})
    except Exception as e:
        print("Delaunay failed:", e)
        
    crack_lines = []
    if num_cracks > 0:
        for _ in range(num_cracks):
            start_idx = np.random.randint(0, len(shifted_pts))
            sx, sy, sz = shifted_pts[start_idx]
            
            crack_points = []
            for step in range(5):
                crack_points.append((
                    sx + np.random.uniform(-1.0, 1.0),
                    sy + np.random.uniform(-1.0, 1.0),
                    sz + 0.1 
                ))
            msp.add_polyline3d(crack_points, dxfattribs={'layer': 'CRACKS'})
            crack_lines.append(crack_points)
            
        # Add Water Plane (simulation of water seeping into lowest areas)
        x_min, x_max = np.min(shifted_pts[:, 0]), np.max(shifted_pts[:, 0])
        y_min, y_max = np.min(shifted_pts[:, 1]), np.max(shifted_pts[:, 1])
        water_z = 0.05 # slightly above the deepest pothole/crack logic
        
        msp.add_3dface([
            (x_min, y_min, water_z),
            (x_max, y_min, water_z),
            (x_max, y_max, water_z),
            (x_min, y_max, water_z)
        ], dxfattribs={'layer': 'WATER_LINE'})
            
    from ezdxf import bbox
    bx = bbox.extents(msp)
    if bx.has_data:
        doc.header['$EXTMIN'] = bx.extmin
        doc.header['$EXTMAX'] = bx.extmax
        height = bx.extmax.y - bx.extmin.y if (bx.extmax.y - bx.extmin.y) > 0 else 10
        doc.set_modelspace_vport(center=bx.center, height=height)
            
    doc.saveas(output_path)
    
    # Generate .obj file for the WebGL CAD Viewer
    obj_path = output_path.replace('.dxf', '.obj')
    with open(obj_path, 'w') as f:
        f.write("# Cyvl Generated CAD Model\n")
        f.write("o Street_Mesh\n")
        for pt in shifted_pts:
            f.write(f"v {pt[0]} {pt[1]} {pt[2]}\n")
            
        try:
            for simplex in tri.simplices:
                # obj indices are 1-based
                f.write(f"f {simplex[0]+1} {simplex[1]+1} {simplex[2]+1}\n")
        except:
            pass
            
        f.write("o Cracks\n")
        # To draw lines in OBJ, we define the vertices then 'l'
        v_idx = len(shifted_pts) + 1
        for crack in crack_lines:
            for pt in crack:
                f.write(f"v {pt[0]} {pt[1]} {pt[2]}\n")
            # Write line segment
            line_indices = " ".join([str(v_idx + i) for i in range(len(crack))])
            f.write(f"l {line_indices}\n")
            v_idx += len(crack)
            
    return True, vol, obj_path
