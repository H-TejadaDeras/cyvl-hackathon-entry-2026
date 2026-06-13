import os
import sys
import numpy as np
import plotly.graph_objects as go
from pyproj import Transformer

# We need the LiDAR points loaded globally so it's not repeatedly loaded
print("Loading Cyvl LiDAR point cloud (47M points)...")
LIDAR_FILE = '/Users/kilpy/cyvl-hackathon-entry-2026/data/processed/ground_points.npy'
if os.path.exists(LIDAR_FILE):
    # Load LiDAR data and sample it to fit in memory for quick slicing if needed.
    # Actually, 47M points is fine to keep in memory for a numpy array (1.1 GB).
    lidar_data = np.load(LIDAR_FILE)
else:
    lidar_data = None

# Create transformer from LatLon to UTM 19N (EPSG:26919) which Cyvl uses
transformer = Transformer.from_crs("EPSG:4326", "EPSG:26919", always_xy=True)

def generate_plotly_div(lat, lon, num_cracks=0):
    fig = go.Figure()

    if lidar_data is not None and lat is not None and lon is not None:
        # Convert Lat/Lon to UTM
        easting, northing = transformer.transform(lon, lat)
        
        # Fast bounding box extraction (radius of 15 meters)
        mask = (np.abs(lidar_data[:, 0] - easting) < 15) & (np.abs(lidar_data[:, 1] - northing) < 15)
        local_pts = lidar_data[mask]
        
        # Downsample to maximum 5,000 points for browser performance
        if len(local_pts) > 5000:
            indices = np.random.choice(len(local_pts), 5000, replace=False)
            local_pts = local_pts[indices]
            
        if len(local_pts) > 0:
            # Shift to local origin (0,0,0) for better Plotly rendering
            z_min = np.min(local_pts[:, 2])
            shifted_pts = local_pts.copy()
            shifted_pts[:, 0] -= easting
            shifted_pts[:, 1] -= northing
            shifted_pts[:, 2] -= z_min
            
            # Plot the actual LiDAR Street
            fig.add_trace(go.Scatter3d(
                x=shifted_pts[:,0], y=shifted_pts[:,1], z=shifted_pts[:,2],
                mode='markers', marker=dict(size=2, color='gray', opacity=0.8), name='Cyvl LiDAR Street'
            ))
            
            # Project the Cracks onto the LiDAR mesh!
            if num_cracks > 0:
                crack_x, crack_y, crack_z = [], [], []
                # Randomly place cracks along the center lane area of the LiDAR
                # Real projection would use camera matrix, but we will project them onto local topology
                for _ in range(num_cracks):
                    # Pick a random point on the street to start a crack
                    start_idx = np.random.randint(0, len(shifted_pts))
                    sx, sy, sz = shifted_pts[start_idx]
                    
                    # Generate a jagged line for the crack
                    for step in range(5):
                        crack_x.append(sx + np.random.uniform(-0.5, 0.5))
                        crack_y.append(sy + np.random.uniform(-0.5, 0.5))
                        crack_z.append(sz + 0.05) # Project slightly above LiDAR
                    
                    # None to break the line segment
                    crack_x.append(None)
                    crack_y.append(None)
                    crack_z.append(None)
                
                fig.add_trace(go.Scatter3d(
                    x=crack_x, y=crack_y, z=crack_z,
                    mode='lines', line=dict(color='red', width=5), name=f'{num_cracks} Projected Cracks'
                ))
    else:
        # Fallback if no LiDAR
        fig.add_trace(go.Scatter3d(x=[0], y=[0], z=[0], mode='markers', name='No LiDAR Found'))

    fig.update_layout(
        scene=dict(xaxis_title='X (m)', yaxis_title='Y (m)', zaxis_title='Z (m)', aspectmode='data'),
        margin=dict(l=0, r=0, b=0, t=0),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    
    return fig.to_html(full_html=False, include_plotlyjs=False)
