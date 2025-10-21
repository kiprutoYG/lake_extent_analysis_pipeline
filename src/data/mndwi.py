import rasterio
import os
import logging
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
        self.processed = config.processed_data_dir
        
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
        
    def fill_gaps_07(self):
        '''
        Fills the strips of empty data present in 2007 image
        '''
        path = os.path.join(self.processed, '2007_mndwi_watermask.tif')
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
                    
            
    def run_mndwi(self):
        '''
        Main entry point to run the mndwi calculation pipeline
        '''
        #find bands 
        landsat_2007_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2007.tif'), 'green')
        landsat_2007_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2007.tif'), 'swir16')
        landsat_2016_green = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2016.tif'), 'green')
        landsat_2016_swir = self.find_band(os.path.join(self.raw_dir, 'landsat-c2-l2_2016.tif'), 'swir16')
        sentinel_2020_green = self.find_band(os.path.join(self.raw_dir, 'sentinel-2-l2a_2020.tif'), 'B03')
        sentinel_2020_swir = self.find_band(os.path.join(self.raw_dir, 'sentinel-2-l2a_2020.tif'), 'B11')
        sentinel_2025_green = self.find_band(os.path.join(self.raw_dir, 'sentinel-2-l2a_2025.tif'), 'B03')
        sentinel_2025_swir = self.find_band(os.path.join(self.raw_dir, 'sentinel-2-l2a_2025.tif'), 'B11')
        
        #calculate mndwi
        self.mndwi_calc(landsat_2016_green, landsat_2016_swir, '2016')
        self.mndwi_calc(landsat_2007_green, landsat_2007_swir, '2007')
        self.mndwi_calc(sentinel_2020_green, sentinel_2020_swir, '2020')
        self.mndwi_calc(sentinel_2025_green, sentinel_2025_swir, '2025')
        self.fill_gaps_07()
        
        