import geopandas as gpd
import rasterio
import os
from pathlib import Path
import zipfile

def ensure_dir_exists(dir_path: str):
    '''
    Create a directory if it does not exist.
    '''
    Path(dir_path).mkdir(parents=True, exist_ok=True)

def read_raster(file: str):
    '''
    Reads a raster file into dataset array
    '''
    with rasterio.open(file) as src:
        return src.read(1), src.profile
    
def write_raster(output_path: str, array, profile):
    """Write a raster safely."""
    ensure_dir_exists(os.path.dirname(output_path))
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(array, 1)
        
def kmz_to_shp(kmz_file: str, out_dir: str):
    '''
    Convert AOI kmz file to shapefile
    '''
    ensure_dir_exists(os.path.dirname(out_dir))
    with zipfile.ZipFile(kmz_file, 'r') as kmz:
        kmz.extractall(out_dir)

    # Locate extracted KML file
    for root, dirs, files in os.walk(out_dir):
        for file in files:
            if file.endswith(".kml"):
                kml_path = os.path.join(root, file)

    # Read KML as GeoDataFrame
    gdf = gpd.read_file(kml_path, driver='KML')

    # Export to Shapefile
    shp_path = os.path.join(out_dir, os.path.splitext(os.path.basename(kmz_file))[0] + ".shp")
    gdf.to_file(shp_path)

    print(f"Converted {kmz_file} → {shp_path}")
    return shp_path

def read_vector(file: str):
    '''
    Reads a vector file into a GeoDataFrame
    '''
    return gpd.read_file(file)

def write_vector(output_path: str, gdf: gpd.GeoDataFrame):
    '''Write a GeoDataFrame to a vector file.'''
    ensure_dir_exists(os.path.dirname(output_path))
    gdf.to_file(output_path)