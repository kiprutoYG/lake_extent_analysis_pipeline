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
        self.analyze_shoreline()
        
                    
    