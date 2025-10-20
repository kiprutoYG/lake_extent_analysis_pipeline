import planetary_computer
import logging
from pystac_client import Client
import geopandas as gpd
from pystac.extensions.eo import EOExtension as eo
import odc.stac
import rioxarray as rio
import os

class DataLoader:
    '''
    The main class that fetches satellite data from planetary computer in cloud optimized geotiff format
    '''
    def __init__(self, config):
        self.logger = logging.getLogger('DataDownloader')
        self.config = config
        self.aoi_path = config.aoi_path
        self.stac_url = config.stac_url
        self.sentinel_collection = config.sentinel_collection
        self.landsat_collection = config.landsat_collection
        self.dem_collection = config.dem_collection
        self.cloud_cover = config.cloud_cover_threshold
        self.date_ranges = config.date_ranges
        self.raw_dir = config.raw_data_dir
        self.target_crs = config.target_crs
        
        self.logger.info('Data Downloader Initialized.')
        
    def load_aoi(self):
        '''
        Loads the shapefile for area of interest into gdf
        '''
        self.logger.info(f'Getting area of interest from {self.aoi_path}')
        aoi_gdf = gpd.read_file(self.aoi_path)
        return aoi_gdf.to_crs('EPSG:4326')
    
    def get_collection_by_year(self, year):
        '''
        Selects the appropriate collection for a certain year
        '''
        if year <= 2016:
            return self.config.landsat_collection
        else:
            return self.config.sentinel_collection
        
    def fetch_data(self):
        '''
        Connects and pulls data from the stac url for specific year and specific satellite mission
        :returns: cloud optimized geotiffs
        '''
        aoi = self.load_aoi()
        minx, miny, maxx, maxy = aoi.total_bounds 
        bbox = [minx, miny, maxx, maxy]
        client = Client.open(self.stac_url, modifier=planetary_computer.sign_inplace,)
        self.logger.info('Connected to stac url successfully.')
        
        downloaded_files = []
        for date_range in self.date_ranges:
            start, end = date_range[0], date_range[1]
            year = int(start[:4])
            collection = self.get_collection_by_year(year)
            self.logger.info(f'Getting collection for year: {year}...')
            
            search = client.search(
                collections=[collection],
                intersects= aoi.geometry.iloc[0].__geo_interface__,
                datetime= f'{start}/{end}',
                query={"eo:cloud_cover": {"lt": self.cloud_cover}}
            )
            search_dem = client.search(
                collections = [self.dem_collection],
                intersects = aoi.geometry.iloc[0].__geo_interface__,
            )
            dem_items = list(search_dem.items())
            items = list(search.items())
            if not items:
                self.logger.info(f'Could not get imagery for year {year}')
                continue
            
            selected_item = min(items, key=lambda item: eo.ext(item).cloud_cover)
            selected_dem = dem_items[0]
            self.logger.info(f'Selected {selected_item.id} with {selected_item.properties['eo:cloud_cover']}% cloud cover')
            try:
                if collection == 'landsat-c2-l2':
                    bands_of_interest = ["nir08", "red", "green", "blue", "swir16"]
                    data = odc.stac.load(
                        items,
                        bands=bands_of_interest,
                        bbox=bbox,
                        groupby="solar_day",  # ensures same-day scenes are grouped
                        chunks={},
                        crs=self.target_crs,
                        resolution=30
                    )
                    # Mosaic multiple tiles into one
                    if "time" in data.dims:
                        data = data.isel(time=0)

                    data = data.mosaic(dim="time") if "time" in data.dims else data
                else:
                    bands_of_interest = ['B02', 'B03', 'B04', 'B11']
                    
                    data = odc.stac.stac_load(
                        [selected_item], bands=bands_of_interest, bbox=bbox
                    ).isel(time=0)
                selected_dem = odc.stac.stac_load(
                    [selected_dem], bbox=bbox
                ).isel(time=0)
                data = data.rio.reproject(self.target_crs)
                out_path = os.path.join(self.raw_dir, f'{collection}_{year}.tif')
                dem_path = os.path.join(self.raw_dir, f'dem.tif')
                self.logger.info(f'Saving item {selected_item.id} for year {year} to {out_path}')
                data.rio.to_raster(out_path)
                selected_dem = selected_dem.rio.reproject(self.target_crs)
                selected_dem.rio.to_raster(dem_path)
                downloaded_files.append(out_path)
            except KeyError:
                self.logger.info(f'Could not download imagery for {collection}, year {year}')
                continue
        self.logger.info(f"Data download complete for {len(downloaded_files)} years.")
        return downloaded_files