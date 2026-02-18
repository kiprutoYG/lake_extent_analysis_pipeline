import rasterio
import os
import logging
from shapely.geometry import shape
from rasterio.features import shapes
from shapely.geometry import Polygon, MultiPolygon
import numpy as np
import geopandas as gpd
import glob
import rioxarray as rio
from skimage.morphology import remove_small_objects, binary_closing, disk
from skimage.morphology import opening


class Mndwi:
    '''
    The main class to calculate the modified normalized difference water index, which will enable masking of water extent. 
    The mndwi is a green and short wave infrared ratio
    '''
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger('MNDWI_Calculator')
        self.raw_dir = config.raw_data_dir
        self.results = config.results_dir
        self.processed = config.processed_data_dir
        self.threshold = config.threshold
        
    def find_band(self, filepath, bandname):
        '''
        Finds the bands used to calculate MNDWI based on the specific satellite mission dataset
        :param filepath: The filepath containing the satellite dataset to analyze
        :param bandname: The name of the individual band to find
        '''
        ds = rio.open_rasterio(filepath)
        band_found = None

        # Open the file with rasterio to inspect per-band descriptions
        with rasterio.open(filepath) as src:
            descriptions = src.descriptions  # tuple of strings or Nones

        for i in range(len(descriptions)):
            desc = descriptions[i]
            # Make sure desc is a string
            if isinstance(desc, (tuple, list)):
                desc = " ".join([str(d) for d in desc])
            elif desc is None:
                desc = ""

            if bandname.lower() in desc.lower():
                band_found = ds.isel(band=i)
                break

        if band_found is None:
            # fallback – check if bandname appears in filename
            fname = os.path.basename(filepath).lower()
            if bandname.lower() in fname:
                band_found = ds.isel(band=0)
            else:
                raise ValueError(f"Band '{bandname}' not found in {filepath}")

        band_found.name = bandname
        return band_found
    
    def mndwi_calc(self, green, swir, outfile_basename):
        '''
        Calculates the Modified Normalized Difference Water Index
        '''
        green = green.astype('float32')
        swir = swir.astype('float32')
        mndwi = (green - swir) / (green + swir)
        mndwi.name = "MNDWI"
        
        out_path = os.path.join(self.processed, f"{outfile_basename}_mndwi.tif")
        mndwi.rio.to_raster(out_path)
        self.logger.info(f"MNDWI saved to {out_path}")
        
    def fill_gaps(self, path):
        '''
        Fills the strips of empty data present in 2007 image
        '''
        # easier approach: use rasterio.open to read meta then write
        with rasterio.open(path) as src:
            mask = src.read(1).astype(bool)
            profile = src.profile.copy()
            # Morphological cleaning
        selem = disk(3)
        mask_closed = binary_closing(mask, selem)
        mask_clean = remove_small_objects(mask_closed, min_size=500)
        mask_clean = opening(mask_clean, selem)
        # Update metadata for uint8 output
        profile.update(dtype=rasterio.uint8, count=1, compress='lzw')

        # Save cleaned mask
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(mask_clean.astype('uint8'), 1)
            
    def create_mask(self, mndwi_path, connectivity = 4):
        '''
        Creates a water mask based on the threshold and writes to disk
        '''
        base = os.path.splitext(os.path.basename(mndwi_path))[0]
        year = base.split('_')[0]
        raster_out_path = os.path.join(self.processed, 'masks', f'{base}_watermask.tif')
        vector_out_path = os.path.join(self.processed, 'masks', f'{base}_watermask.shp')
        dissolved_out_path = os.path.join(self.results, f'lake_{year}.shp')
        self.logger.info(f'Reading mndwi file {base}')
        with rasterio.open(mndwi_path) as src:
            arr = src.read(1, masked =True)
            transform = src.transform
            crs = src.crs
        mask = arr > self.threshold
        
        meta = src.meta.copy()
        meta.update(
            dtype= 'uint8',
            count=1,
            compress='lzw'
        )
        with rasterio.open(raster_out_path, 'w', **meta) as dest:
            dest.write(mask.astype(np.uint8), 1)
        self.logger.info(f'Saved the raster to {raster_out_path}')
            
        
        #vectorization
        self.logger.info('Vectorizing the mask')
        mask_arr = np.where(mask, 1, 0).astype(np.uint8)

        # Ensure same shape as raster
        if mask_arr.shape != arr.shape:
            raise ValueError(f"Shape mismatch: mask {mask_arr.shape} vs raster {arr.shape}")

        # Generate polygons
        shapes_gen = shapes(mask_arr, mask=mask_arr.astype(bool), transform=transform, connectivity=connectivity)
        polygons = []
      
        for geom, val in shapes_gen:
            if val == 1:
                polygons.append(geom)
                
        if polygons:
            gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries([shape(p) for p in polygons]), crs=crs)
            gdf.to_file(vector_out_path)
            gdf_dissolved = gdf.dissolve()
            gdf_dissolved = gdf_dissolved.explode(index_parts=False).reset_index(drop=True)
            # 3. compute area in m² (ensure projected CRS in meters)
            if gdf_dissolved.crs.is_geographic:
                gdf_dissolved = gdf_dissolved.to_crs(epsg=32636)  # your UTM

            gdf_dissolved['area_m2'] = gdf_dissolved.geometry.area

            # 4. remove small polygons below threshold (e.g., < 1000 m²)
            gdf_dissolved = gdf_dissolved[gdf_dissolved['area_m2'] >= 1000]

            # 5. fix invalid geometries & optional simplification
            gdf_dissolved['geometry'] = gdf_dissolved['geometry'].buffer(0)
            gdf_dissolved = gdf_dissolved[gdf_dissolved.geometry.is_valid]
            gdf_dissolved['geometry'] = gdf_dissolved['geometry'].simplify(tolerance=5)  # in meters

            # 6. dissolve again to single polygon if desired
            gdf_dissolved = gdf.dissolve().reset_index(drop=True)
            gdf_dissolved = gpd.GeoDataFrame(geometry=[gdf_dissolved.buffer(60).unary_union], crs=gdf.crs)
            gdf_dissolved["geometry"] = gdf_dissolved.geometry.buffer(-30)
            gdf_dissolved['area_km2'] = gdf_dissolved.geometry.area / 1e6
            gdf_dissolved.to_file(dissolved_out_path)
            logging.info(f"Saved vectorized water polygons to {vector_out_path}")
        else:
            logging.warning("No water polygons found above threshold!")
                    
            
    def run_mndwi(self):
        '''
        Main entry point to run the mndwi calculation pipeline
        '''
        #find bands 
        landsat_2001_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2001.tif'), 'green')
        landsat_2001_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2001.tif'), 'swir16')
        landsat_2007_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2007.tif'), 'green')
        landsat_2007_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2007.tif'), 'swir16')
        landsat_2013_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2013.tif'), 'green')
        landsat_2013_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2013.tif'), 'swir16')
        landsat_2016_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2016.tif'), 'green')
        landsat_2016_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2016.tif'), 'swir16')
        landsat_2019_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2019.tif'), 'green')
        landsat_2019_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2019.tif'), 'swir16')
        landsat_2025_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2025.tif'), 'green')
        landsat_2025_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2025.tif'), 'swir16')
        
        #calculate mndwi
        self.mndwi_calc(landsat_2016_green, landsat_2016_swir, '2016')
        self.mndwi_calc(landsat_2007_green, landsat_2007_swir, '2007')
        self.mndwi_calc(landsat_2001_green, landsat_2001_swir, '2001')
        self.mndwi_calc(landsat_2013_green, landsat_2013_swir, '2013')
        self.mndwi_calc(landsat_2019_green, landsat_2019_swir, '2019')
        self.mndwi_calc(landsat_2025_green, landsat_2025_swir, '2025')
        self.create_mask(os.path.join(self.processed, '2001_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2007_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2013_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2016_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2019_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2025_mndwi.tif'))
        self.fill_gaps(os.path.join(self.processed, 'masks', '2007_mndwi_watermask.tif'))
        self.fill_gaps(os.path.join(self.processed, 'masks', '2016_mndwi_watermask.tif'))
        
        
        