import rasterio
import geopandas as gpd
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.geometry import Polygon, MultiPolygon
import logging
import numpy as np
import os
import osmnx as ox
import glob

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
            gdf_dissolved = gdf.dissolve()
            gdf_dissolved = gdf_dissolved.explode(index_parts=False).reset_index(drop=True)
            # 3. compute area in m² (ensure projected CRS in meters)
            if gdf_dissolved.crs.is_geographic:
                gdf_dissolved = gdf_dissolved.to_crs(epsg=32636)  # your UTM

            gdf_dissolved['area_m2'] = gdf_dissolved.geometry.area

            # 4. remove small polygons below threshold (e.g., < 500 m²)
            gdf_dissolved = gdf_dissolved[gdf_dissolved['area_m2'] >= 500]

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
            
    def analyze_shoreline(self):
        '''
        Take the lake extents for different years and create new layers from them
        '''
        file_2007 = os.path.join(self.results, 'lake_2007.shp')
        file_2016 = os.path.join(self.results, 'lake_2016.shp')
        file_2025 = os.path.join(self.results, 'lake_2025.shp')
        growth_area_path = os.path.join(self.results, 'growth_area.shp')
        buildings_out_path = os.path.join(self.processed, 'buildings.gpkg')
        facilities_out_path = os.path.join(self.processed, 'facilities.gpkg')
        roads_out_path = os.path.join(self.processed, 'roads.gpkg')
        lake_2007 = gpd.read_file(file_2007)
        lake_2016 = gpd.read_file(file_2016)
        lake_2025 = gpd.read_file(file_2025)
        
        #what is the change in areas
        area_change_25_16 = lake_2025["area_km2"].values[0] - lake_2016["area_km2"].values[0]
        area_change_16_07 = lake_2016['area_km2'].values[0] - lake_2007['area_km2'].values[0]
        self.logger.info(f'Lake extent increased {area_change_16_07:.3f}km2 btn 2016 and 2007')
        self.logger.info(f'Lake extent increased {area_change_25_16:.3f}km2 btn 2016 and 2025')
        
        #what is the growth area
        growth_area = gpd.overlay(lake_2025, lake_2007, how="difference")
        growth_area.to_file(growth_area_path)
        growth_area = growth_area.to_crs("EPSG:32636")  # UTM Zone 36N for Kenya
        area_km2 = growth_area.area.sum() / 1e6
        self.logger.info(f'Lake expanded by {area_km2}km2 btn 2007 and 2025')
        
        #what infrastructure were affected(using openstreetmap)
        growth_area = growth_area.to_crs("EPSG:4326")
        minx, miny, maxx, maxy = growth_area.total_bounds 
        bbox = [minx, miny, maxx, maxy]

        # Download OSM features
        self.logger.info('Getting infrastructure shapes from osm')
        buildings = ox.features_from_bbox(bbox, tags={"building": True})
        roads = ox.features_from_bbox(bbox, tags={"highway": True})
        facilities = ox.features_from_bbox(bbox, tags={"amenity": True})

        # Save or filter later
        # Delete all old shapefile components if they exist
        for path in [buildings_out_path, facilities_out_path, roads_out_path]:
            for f in glob.glob(path.replace('.shp', '.*')):
                os.remove(f)
        buildings.to_file(buildings_out_path, driver="GPKG")
        roads.to_file(roads_out_path, driver="GPKG")
        facilities.to_file(facilities_out_path, driver="GPKG")
        self.logger.info('Saved all infrastructure shapefiles.')

              
        
    def run_extent(self):
        '''
        Main entry point to running the vectorization and binary masking of mndwi
        '''
        self.create_mask(os.path.join(self.processed, '2007_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2016_mndwi.tif'))
        self.create_mask(os.path.join(self.processed, '2025_mndwi.tif'))
        self.analyze_shoreline()
        
        
        
        #
                    
    