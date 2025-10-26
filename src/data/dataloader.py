import planetary_computer
import logging
from pystac_client import Client
import geopandas as gpd
from pystac.extensions.eo import EOExtension as eo
from ..utils.io_utils import read_vector
import xarray as xr
import odc.stac
import rioxarray as rio
import os
import fsspec

class DataLoader:
    '''
    The main class that fetches satellite data from planetary computer in cloud optimized geotiff format
    '''
    def __init__(self, config):
        self.logger = logging.getLogger('DataDownloader')
        self.config = config
        self.aoi_path = config.aoi_path
        self.stac_url = config.stac_url
        self.landsat_collection = config.landsat_collection
        self.dem_collection = config.dem_collection
        self.era5 = config.era5_collection
        self.cloud_cover = config.cloud_cover_threshold
        self.years = config.years
        self.raw_dir = config.raw_data_dir
        self.target_crs = config.target_crs
        
        self.logger.info('Data Downloader Initialized.')
        
    
        
    def fetch_data(self):
        '''
        Connects and pulls data from the stac url for specific year and specific satellite mission
        :returns: cloud optimized geotiffs in memory
        '''
        aoi = read_vector(self.aoi_path).to_crs('EPSG:4326')
        minx, miny, maxx, maxy = aoi.total_bounds 
        bbox = [minx, miny, maxx, maxy]
        client = Client.open(self.stac_url, modifier=planetary_computer.sign_inplace,)
        self.logger.info('Connected to stac url successfully.')
        # self._fetch_landsat(client, aoi, bbox)
        # self._fetch_dem(client, aoi, bbox)
        self._fetch_precip(client, aoi, bbox)
        
    
    def _fetch_landsat(self, client, aoi, bbox) -> list[str]:
        downloaded_files = []
        for year in self.years:
            start, end = f'{year}-10-01', f'{year}-10-31'
            search = client.search(
                collections=[self.landsat_collection],
                intersects= aoi.geometry.iloc[0].__geo_interface__,
                datetime= f'{start}/{end}',
                query={"eo:cloud_cover": {"lt": self.cloud_cover}}
            )
            items = list(search.items())
            if not items:
                self.logger.info(f'Could not get imagery for year {year}')
                continue
            
            selected_item = min(items, key=lambda item: eo.ext(item).cloud_cover)
            self.logger.info(f'Selected {selected_item.id} with {selected_item.properties['eo:cloud_cover']}% cloud cover')
            try:
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
                #ensure it is in projected crs
                data = data.rio.reproject(self.target_crs)
                out_path = os.path.join(self.raw_dir, f'{self.landsat_collection}_{year}.tif')
                self.logger.info(f'Saving item {selected_item.id} for year {year} to {out_path}')
                data.rio.to_raster(out_path)
                downloaded_files.append(out_path)
            except KeyError:
                self.logger.info(f'Could not download imagery for {self.landsat_collection}, year {year}')
                continue
        self.logger.info(f"Data download complete for {len(downloaded_files)} years.")
        return downloaded_files
    
    def _fetch_dem(self, client, aoi, bbox) -> None:
        search_dem = client.search(
                collections = [self.dem_collection],
                intersects = aoi.geometry.iloc[0].__geo_interface__,
            )
        dem_items = list(search_dem.items())
        #get first item
        selected_dem = dem_items[0]
        try:
            selected_dem = odc.stac.stac_load(
                    [selected_dem], bbox=bbox
                ).isel(time=0)
            selected_dem = selected_dem.rio.reproject(self.target_crs)
            dem_path = os.path.join(self.raw_dir, f'dem.tif')
            selected_dem.rio.to_raster(dem_path)
            self.logger.info(f'Saving the dem to {dem_path}')
        except KeyError:
            self.logger.info('Could not download dem raster.')
        
    def _fetch_precip(self, client, aoi, bbox) -> list[str]:
        downloaded_files = []
        for year in self.years:
            date = f'{year}-08'
            search = client.search(
                collections=[self.era5],
                intersects= aoi.geometry.iloc[0].__geo_interface__,
                datetime= date,
                query={"era5:kind": {"eq": "fc"}}
            )
            items = list(search.items())
            if not items:
                self.logger.info(f'Could not get any items for {self.era5}, date: {date}')
                continue
            selected_item = items[0]
            try:
                #build the dataset
                signed_item = planetary_computer.sign(selected_item)
                
                #pick precipitation item only
                precip_asset = signed_item.assets["precipitation_amount_1hour_Accumulation"]
                
                ds = xr.open_dataset(precip_asset.href)
                minx, miny, maxx, maxy = bbox
                ds_aoi = ds.isel(longitude=slice(minx, maxx), latitude=slice(maxy, miny))
                var_name = list(ds_aoi.data_vars.keys())[0]  # usually 'precipitation_amount_1hour_Accumulation'
                precip = ds_aoi[var_name].rio.reproject(self.target_crs)
            
                #out path
                out_precip = os.path.join(self.raw_dir, f'{self.era5}_{year}.tif')
                precip.rio.to_raster(out_precip)
                self.logger.info(f'Saving the ERA5 dataset to {out_precip}')
                downloaded_files.append(out_precip)
            
            except KeyError:
                self.logger.info('Could not download era5 raster.')
                continue
        self.logger.info(f"Data download complete for {len(downloaded_files)} years.")
        return downloaded_files
            