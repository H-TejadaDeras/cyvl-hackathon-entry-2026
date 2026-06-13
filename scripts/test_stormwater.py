import os
import sys
import numpy as np

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'cyvl-hackathon-entry-2026')))

from curbrisk.scoring.stormwater import (
    calculate_volume,
    generate_cad_cross_section,
    points_to_landxml,
    ransac_plane_fit,
    get_rotation_matrix
)

def test_stormwater():
    print("Testing get_rotation_matrix...")
    R = get_rotation_matrix(90, 0, 0)
    print("R matrix:\n", R)
    
    print("\nTesting calculate_volume...")
    # Create some mock surrounding points forming a plane Z=5
    x_surr = np.random.uniform(-10, 10, 100)
    y_surr = np.random.uniform(-10, 10, 100)
    z_surr = 5.0 + np.random.normal(0, 0.01, 100) # healthy points roughly at Z=5
    surrounding_points = np.column_stack((x_surr, y_surr, z_surr))
    
    # Create some mock isolated points forming a depression inside a polygon
    # Let's say a square from -2 to 2, with Z dipping down to 4 in the middle
    x_iso = np.random.uniform(-2, 2, 200)
    y_iso = np.random.uniform(-2, 2, 200)
    # distance from center
    dist = np.sqrt(x_iso**2 + y_iso**2)
    # dip is max 1.0 at center, fading out to 0 at dist=2
    z_iso = 5.0 - np.maximum(0, 1.0 - dist/2.0)
    isolated_points = np.column_stack((x_iso, y_iso, z_iso))
    
    vol, z_surf = calculate_volume(isolated_points, surrounding_points)
    print(f"Calculated Volume: {vol:.3f} m^3, Reference Surface Z: {z_surf:.3f} m")
    
    print("\nTesting DXF generation...")
    # Mock surface points for cross-section (e.g. Y=0 slice)
    # Sort isolated points by X
    slice_points = sorted([p for p in isolated_points if abs(p[1]) < 0.5], key=lambda p: p[0])
    slice_points = [(p[0], p[1], p[2]) for p in slice_points]
    
    # Mock crack bounds 2D-in-3D
    bounds = [[-2, -2, 5], [2, -2, 5], [2, 2, 5], [-2, 2, 5]]
    
    dxf_path = "test_output.dxf"
    generate_cad_cross_section(dxf_path, slice_points, z_surf, bounds)
    print(f"DXF saved to {dxf_path}")
    
    print("\nTesting LandXML generation...")
    xml_path = "test_output.xml"
    points_to_landxml(xml_path, isolated_points)
    print(f"LandXML saved to {xml_path}")

if __name__ == "__main__":
    test_stormwater()
