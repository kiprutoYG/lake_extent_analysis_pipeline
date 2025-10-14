import rasterio
import os
import logging
import rioxarray as rio
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
        
    def find_band(self, directory):
        '''
        Finds the bands used to calculate MNDWI based on the specific satellite mission dataset
        :param directory: The directory containing the satellite datasets to analyze
        '''
        for file in os.listdir(directory):
            if 'sentinel' in file.lower() and file.lower().endswith('.tif'):
                green = 'B03'
                swir = 'B11'
            elif 'landsat' in file.lower() and file.lower().endswith('.tif'):
                green = 'green'
                swir = 'swir16'
            
         
        