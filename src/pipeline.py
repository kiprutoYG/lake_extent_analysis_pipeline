import logging
from src.config import Config

#import modules
from src.data.dataloader import DataLoader
class LakeRisePipeline:
    '''
    Main orchestration class for the whole lake rise analysis workflow.
    '''
    def __init__(self, config: Config):
        self.config = config
        self.dataloader = DataLoader(config)
        #logging info to panel
        logging.basicConfig(level=self.config.log_level)
        self.logger = logging.getLogger('LakeRisePipeline')
        self.logger.info('Starting pipeline run')
        
        #modules to use in analysis
        
        
    def run_download(self):
        '''
        Runs only the download part of the pipeline
        '''
        self.logger.info('Downloading data...')
        self.dataloader.fetch_data()
        self.logger.info('Data download complete')
        
    def run_preprocess(self):
        '''
        Run only the preprocessing of the data part of the pipeline
        '''
        self.logger.info('Preprocessing data')
        
    def run_full_pipeline(self):
        '''
        Run every job in the pipeline
        '''
        self.run_download()
        