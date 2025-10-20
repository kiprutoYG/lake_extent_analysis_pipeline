from src.config import Config
from src.pipeline import LakeRisePipeline
import argparse

    
if __name__== "__main__":
    parser = argparse.ArgumentParser(description='Lake Rise Analysis Pipeline')
    parser.add_argument(
        '--stage',
        type=str,
        choices=['download', 'mndwi', 'extent'],
        default='all',
        help='Stage of pipeline to run'
    )
    args = parser.parse_args()
    config = Config()
    pipeline = LakeRisePipeline(config)
    
    if args.stage == 'all':
        pipeline.run_full_pipeline()
    elif args.stage == 'download':
        pipeline.run_download()
    elif args.stage == 'mndwi':
        pipeline.run_mndwi()
    elif args.stage == 'extent':
        pipeline.run_extent_analysis()