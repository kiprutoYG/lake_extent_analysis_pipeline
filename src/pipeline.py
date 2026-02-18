import logging
from src.config import Config

#import modules
from src.data.dataloader import DataLoader
from src.data.mndwi import Mndwi
from src.analysis.extent import ExtentAnalyzer
from src.data.dem_features import DemProcessing
from src.prediction.prediction import Predictor

class LakeRisePipeline:
    '''
    Main orchestration class for the whole lake rise analysis workflow.
    '''
    def __init__(self, config: Config):
        self.config = config
        self.dataloader = DataLoader(config)
        self.mndwi = Mndwi(config)
        self.extent_analyzer = ExtentAnalyzer(config)
        self.dem_features = DemProcessing(config)
        self.predictor = Predictor(config)
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
        
    def process_dem(self) -> None:
        '''
        Run the processing of the dem to get features
        '''
        self.logger.info('Processing DEM...')
        self.dem_features.calculate_features()
        self.logger.info('DEM features calculation complete.')
    
    def run_mndwi(self):
        '''
        Run only mndwi calculation part of pipeline
        '''
        self.logger.info('Calculating MNDWI...')
        self.mndwi.run_mndwi()
        self.logger.info('MNDWI calculation complete')
    
    def run_extent_analysis(self):
        '''
        Run only extent masking part of pipeline
        '''
        self.logger.info('Masking extent...')
        self.extent_analyzer.run_extent()
        self.logger.info('Extent extraction complete.')
        
        
    def run_prediction(self):
        '''
        Run the prediction part of the analysis
        '''
        self.logger.info('Running prediction...')
        self.predictor.train([2007, 2019, 2025])
        self.predictor.predict(2031)
        self.predictor.save_model()
        self.logger.info('Prediction complete.')
        
    def run_full_pipeline(self):
        '''
        Run every job in the pipeline
        '''
        self.run_download()
        self.run_mndwi()
        self.process_dem()
        self.run_extent_analysis()
        self.run_prediction()
        