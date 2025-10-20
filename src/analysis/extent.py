import rasterio
import geopandas as gpd
from rasterio.features import shapes
from shapely.geometry import shape
import logging
import numpy as np
import os

class ExtentAnalyzer:
    '''
    Main class to analyze mndwi images to establish shoreline change metrics for the lake
    '''
    def __init__(self, config) -> None:
        self.config = config
        self.logger = logging.getLogger('ExtentAnalyzer')
        self.raw_dir = config.raw_data_dir
        self.results = config.results_dir
        self.processed = config.processed_data_dir
        self.threshold = config.threshold
        
    def create_mask(self, mndwi_path, connectivity = 4):
        '''
        Creates a water mask based on the threshold and writes to disk
        '''
        base = os.path.splitext(os.path.basename(mndwi_path))[0]
        year = base.split('_')[0]
        raster_out_path = os.path.join(self.processed, f'{base}_watermask.tif')
        vector_out_path = os.path.join(self.processed, f'{base}_watermask.shp')
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
            gdf.dissolve().to_file(dissolved_out_path)
            logging.info(f"Saved vectorized water polygons to {vector_out_path}")
        else:
            logging.warning("No water polygons found above threshold!")
            
    def analyze_shoreline(self, filepath):
        '''
        Take the lake extents for different years and create new layers from them
        '''
        lake = gpd.read_file(filepath)
        base = os.path.splitext(os.path.basename(filepath))[0]
        shore_out_path = os.path.join(self.results, f'{base}_shoreline.shp')
        #how much area did the lake have in each year
        lake['area_km2'] = lake.geometry.area / 1e6
        #where was the shoreline in one boundary not disjoint
        shore = gpd.GeoDataFrame(geometry=lake.boundary, crs=lake.crs)
        shore.to_file(shore_out_path)
        
        return lake 
        
        
        
        
            
        
    def run_extent(self):
        '''
        Main entry point to running the vectorization and binary masking of mndwi
        '''
        self.create_mask(os.path.join(self.processed, '2016_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2020_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2025_mndwi.tif'))
        
        #shorelines
        lake_2016 = self.analyze_shoreline(os.path.join(self.results, 'lake_2016.shp'))
        lake_2020 = self.analyze_shoreline(os.path.join(self.results, 'lake_2020.shp'))
        lake_2025 = self.analyze_shoreline(os.path.join(self.results, 'lake_2025.shp'))
        
        #what is the change in areas
        area_change_20_25 = lake_2025["area_km2"].values[0] - lake_2020["area_km2"].values[0]
        area_change_20_16 = lake_2020['area_km2'].values[0] - lake_2016['area_km2'].values[0]
        self.logger.info(f'Lake extent increased {area_change_20_16}km2 btn 2016 and 2020')
        self.logger.info(f'Lake extent increased {area_change_20_25}km2 btn 2020 and 2025')
        
        # Compute average minimum distance between 2020 and 2025 shorelines
        shore_2016 = gpd.GeoDataFrame(geometry=lake_2016.boundary, crs=lake_2016.crs)
        shore_2020 = gpd.GeoDataFrame(geometry=lake_2020.boundary, crs=lake_2020.crs)
        shore_2025 = gpd.GeoDataFrame(geometry=lake_2025.boundary, crs=lake_2025.crs)
        
        distances_20_25 = [
            shore_2020.distance(geom).min() 
            for geom in shore_2025.geometry
        ]
        distances_16_20 = [
            shore_2016.distance(geom).min() 
            for geom in shore_2020.geometry
        ]


        mean_dist_20_25 = np.mean(distances_20_25)
        mean_dist_16_20 = np.mean(distances_16_20)
        self.logger.info(f'Shoreline changed an average of {mean_dist_20_25} btn 2020 and 2025')
        self.logger.info(f'Shoreline changed an average of {mean_dist_16_20} btn 2016 and 2020')
                    
    