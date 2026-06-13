import numpy as np
import ezdxf
import xml.etree.ElementTree as ET
from scipy.spatial import Delaunay, cKDTree
from pyproj import Transformer
import laspy
from matplotlib.path import Path

# Phase 1: Spatial Join (Reverse Photogrammetry)
def get_rotation_matrix(heading, pitch, roll):
    """
    Convert heading (yaw), pitch, and roll in degrees to a 3x3 rotation matrix.
    Assuming standard right-handed coordinate system.
    """
    # Convert to radians
    h = np.radians(heading)
    p = np.radians(pitch)
    r = np.radians(roll)
    
    # Rotation matrices
    Rz = np.array([
        [np.cos(h), -np.sin(h), 0],
        [np.sin(h),  np.cos(h), 0],
        [0,          0,         1]
    ])
    
    Ry = np.array([
        [ np.cos(p), 0, np.sin(p)],
        [ 0,         1, 0        ],
        [-np.sin(p), 0, np.cos(p)]
    ])
    
    Rx = np.array([
        [1, 0,         0        ],
        [0, np.cos(r), -np.sin(r)],
        [0, np.sin(r),  np.cos(r)]
    ])
    
    return Rz @ Ry @ Rx

def project_2d_to_3d(lat, lon, alt, heading, pitch, roll, polygon_2d, img_w, img_h, laz_path):
    """
    Project 2D polygon boundaries to 3D LiDAR point cloud.
    """
    # 1. Coordinate Unification
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32619", always_xy=True)
    easting, northing = transformer.transform(lon, lat)
    T_cam = np.array([easting, northing, alt])
    R_cam = get_rotation_matrix(heading, pitch, roll)
    
    # 2. Spherical Unwrapping (just documenting the math, actual processing done via reverse projection below)
    frustum_rays = []
    for u, v in polygon_2d:
        theta = (u / img_w - 0.5) * 2 * np.pi
        phi = (0.5 - v / img_h) * np.pi
        d_local = np.array([
            np.cos(phi) * np.sin(theta),
            np.sin(phi),
            np.cos(phi) * np.cos(theta)
        ])
        d_world = R_cam @ d_local
        frustum_rays.append(d_world)
        
    # 3. Frustum Culling
    las = laspy.read(laz_path)
    points = np.vstack((las.x, las.y, las.z)).T
    
    # KD-Tree to filter points beyond 15 meters
    tree = cKDTree(points)
    indices = tree.query_ball_point(T_cam, r=15.0)
    local_points = points[indices]
    
    poly_path = Path(polygon_2d)
    
    isolated_points = []
    surrounding_points = []
    
    for pt in local_points:
        vec = pt - T_cam
        dist = np.linalg.norm(vec)
        if dist == 0:
            continue
        vec_norm = vec / dist
        
        vec_local = np.linalg.inv(R_cam) @ vec_norm
        
        # Reverse spherical unwrapping
        phi = np.arcsin(np.clip(vec_local[1], -1.0, 1.0))
        theta = np.arctan2(vec_local[0], vec_local[2])
        
        u = (theta / (2 * np.pi) + 0.5) * img_w
        v = (0.5 - phi / np.pi) * img_h
        
        if poly_path.contains_point((u, v)):
            isolated_points.append(pt)
        else:
            surrounding_points.append(pt)
            
    return np.array(isolated_points), np.array(surrounding_points)

# Phase 2: Volumetric Regression
def ransac_plane_fit(points, threshold=0.02, max_iters=1000):
    """
    Fit a plane using RANSAC.
    points: (N, 3) array
    Returns: normal vector (3,), point on plane (3,)
    """
    best_inliers = []
    best_plane = None
    
    n_points = points.shape[0]
    if n_points < 3:
        raise ValueError("Not enough points to fit a plane")
        
    for _ in range(max_iters):
        idx = np.random.choice(n_points, 3, replace=False)
        p1, p2, p3 = points[idx]
        
        v1 = p2 - p1
        v2 = p3 - p1
        normal = np.cross(v1, v2)
        norm_length = np.linalg.norm(normal)
        if norm_length < 1e-6:
            continue
        normal = normal / norm_length
        
        vecs = points - p1
        distances = np.abs(np.dot(vecs, normal))
        
        inliers = np.where(distances < threshold)[0]
        if len(inliers) > len(best_inliers):
            best_inliers = inliers
            best_plane = (normal, p1)
            
    return best_plane[0], best_plane[1]

def calculate_volume(isolated_points, surrounding_points):
    """
    Calculate the exact volume of the depression.
    """
    if len(isolated_points) < 3 or len(surrounding_points) < 3:
        return 0.0, None
        
    centroid = np.mean(isolated_points, axis=0)
    tree = cKDTree(surrounding_points)
    k = min(500, len(surrounding_points))
    _, nearest_idx = tree.query(centroid, k=k)
    ref_points = surrounding_points[nearest_idx]
    
    normal, p_ref = ransac_plane_fit(ref_points)
    
    if normal[2] < 0:
        normal = -normal
        
    xy = isolated_points[:, :2]
    try:
        tri = Delaunay(xy)
    except Exception:
        return 0.0, None
        
    volume = 0.0
    for simplex in tri.simplices:
        p1, p2, p3 = isolated_points[simplex]
        
        area = 0.5 * np.abs(
            p1[0]*(p2[1] - p3[1]) + 
            p2[0]*(p3[1] - p1[1]) + 
            p3[0]*(p1[1] - p2[1])
        )
        
        center = (p1 + p2 + p3) / 3.0
        z_surface = p_ref[2] - (normal[0]*(center[0] - p_ref[0]) + normal[1]*(center[1] - p_ref[1])) / normal[2]
        z_crack = center[2]
        
        if z_surface > z_crack:
            volume += area * (z_surface - z_crack)
            
    z_surface_avg = p_ref[2] - (normal[0]*(centroid[0] - p_ref[0]) + normal[1]*(centroid[1] - p_ref[1])) / normal[2]
    
    return volume, z_surface_avg

# Phase 3: ezdxf 3D Cross-Section Generation
def generate_cad_cross_section(output_path, surface_points, water_level, crack_poly_2d_3d):
    """
    Generate DXF cross-section
    """
    doc = ezdxf.new('R2010')
    doc.layers.add("ROAD_PROFILE", color=ezdxf.colors.RED)
    doc.layers.add("WATER_LINE", color=ezdxf.colors.BLUE)
    doc.layers.add("CRACK_BOUNDS", color=ezdxf.colors.GREEN)
    
    msp = doc.modelspace()
    
    # ROAD_PROFILE: 3D polyline of surface points
    if len(surface_points) > 0:
        msp.add_polyline3d(surface_points, dxfattribs={'layer': 'ROAD_PROFILE'})
    
    # WATER_LINE: a flat 3D face at water level
    if len(surface_points) >= 2:
        x_min = min(p[0] for p in surface_points)
        x_max = max(p[0] for p in surface_points)
        y_min = min(p[1] for p in surface_points)
        y_max = max(p[1] for p in surface_points)
        
        msp.add_3dface([
            (x_min, y_min, water_level),
            (x_max, y_min, water_level),
            (x_max, y_max, water_level),
            (x_min, y_max, water_level)
        ], dxfattribs={'layer': 'WATER_LINE'})
        
    # CRACK_BOUNDS
    if len(crack_poly_2d_3d) > 0:
        if isinstance(crack_poly_2d_3d, np.ndarray):
            poly_points = crack_poly_2d_3d.tolist()
        else:
            poly_points = crack_poly_2d_3d
        poly_points.append(poly_points[0]) # close polygon
        msp.add_polyline3d(poly_points, dxfattribs={'layer': 'CRACK_BOUNDS'})
        
    from ezdxf import bbox
    bx = bbox.extents(msp)
    if bx.has_data:
        doc.header['$EXTMIN'] = bx.extmin
        doc.header['$EXTMAX'] = bx.extmax
        height = bx.extmax.y - bx.extmin.y if (bx.extmax.y - bx.extmin.y) > 0 else 10
        doc.set_modelspace_vport(center=bx.center, height=height)
        
    doc.saveas(output_path)

# Phase 4: LandXML TIN Surface Export
def points_to_landxml(output_path, xyz_points, surface_name="CurbRisk_Terrain"):
    """
    Generate LandXML surface
    """
    if len(xyz_points) < 3:
        raise ValueError("Not enough points to generate LandXML TIN")
        
    xy = xyz_points[:, :2]
    tri = Delaunay(xy)
    
    LandXML = ET.Element("LandXML")
    LandXML.set("xmlns", "http://www.landxml.org/schema/LandXML-1.2")
    LandXML.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    LandXML.set("xsi:schemaLocation", "http://www.landxml.org/schema/LandXML-1.2 http://www.landxml.org/schema/LandXML-1.2/LandXML-1.2.xsd")
    LandXML.set("date", "2026-06-13")
    LandXML.set("time", "12:00:00")
    LandXML.set("version", "1.2")
    
    Surfaces = ET.SubElement(LandXML, "Surfaces")
    Surface = ET.SubElement(Surfaces, "Surface")
    Surface.set("name", surface_name)
    
    Definition = ET.SubElement(Surface, "Definition")
    Definition.set("surfType", "TIN")
    
    Pnts = ET.SubElement(Definition, "Pnts")
    for i, pt in enumerate(xyz_points):
        P = ET.SubElement(Pnts, "P")
        P.set("id", str(i + 1))
        # LandXML coordinates are Northing Easting Elevation
        P.text = f"{pt[1]:.3f} {pt[0]:.3f} {pt[2]:.3f}"
        
    Faces = ET.SubElement(Definition, "Faces")
    for simplex in tri.simplices:
        F = ET.SubElement(Faces, "F")
        F.text = f"{simplex[0]+1} {simplex[1]+1} {simplex[2]+1}"
        
    tree = ET.ElementTree(LandXML)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
