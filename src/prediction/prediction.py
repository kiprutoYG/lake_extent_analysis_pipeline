import os
import rasterio
import numpy as np
import geopandas as gpd
from rasterio.warp import reproject, calculate_default_transform, Resampling
from sklearn.ensemble import RandomForestClassifier
from rasterio.merge import merge
from rasterio import features
from scipy.ndimage import distance_transform_edt
from rasterio.mask import mask
from rasterio.plot import show
import joblib
import logging

class Predictor:
    '''
    This is the entire class that runs the prediction for how the lake will have expanded by the year 2030.
    It begins by running the extension analysis for 2025 so as to use this as validation before 2030 can be predicted.
    '''
    def __init__(self, config, model_path = None) -> None:
        self.config = config
        self.logger = logging.getLogger('Predictor')
        self.results = config.results_dir
        self.processed = config.processed_data_dir
        self.masks = os.path.join(self.processed, 'masks')
        self.features = os.path.join(self.processed, 'features')
        
        #load model if available, and if not: initialize RF
        if model_path and os.path.exists(model_path):
            self.model = joblib.load(model_path)
            self.logger.info(f"Loaded existing model from {model_path}")
        else:
            self.model = RandomForestClassifier(
                n_estimators=100, 
                random_state=42,
                n_jobs=-1
            )
            
        
    def _load_raster(self, path):
        with rasterio.open(path) as src:
            arr = src.read(1, masked=True)
            profile = src.profile
        return arr, profile

    def _distance_from_shoreline(self, years: list) -> None:
        '''
        Creates a distance from shoreline raster using euclidean distance tool
        '''
        for year in years:
            shoreline_path = os.path.join(self.results, f'lake_{year}.shp')
            shoreline = gpd.read_file(shoreline_path).to_crs('EPSG:32626')
            
            # Define raster metadata (extent, resolution, CRS)
            template = rasterio.open(os.path.join(self.masks, '2025_mndwi_watermask_down.tif'))  # e.g. one of your predictors
            meta = template.meta.copy()
            
            # Rasterize shoreline (1 for shoreline, 0 elsewhere)
            shoreline_raster = features.rasterize(
                ((geom, 1) for geom in shoreline.geometry),
                out_shape=(meta['height'], meta['width']),
                transform=meta['transform'],
                fill=0,
                dtype='uint8'
            )

            # Compute Euclidean distance (pixel units)
            distance = distance_transform_edt(shoreline_raster == 0)

            # Convert to meters (multiply by pixel size)
            pixel_size = meta['transform'][0]
            distance_m = distance * pixel_size

            # Save the result
            out_path = os.path.join(self.features, f'distance_from_shoreline_{year}.tif')
            meta.update(dtype=rasterio.float32)
            with rasterio.open(out_path, 'w', **meta) as dst:
                dst.write(distance_m.astype(np.float32), 1)
            self.logger.info('Created distance from shoreline rasters and saved to features.')
        
        
    def _coregister_raster(self, src_path: str, dest_path: str, ref_path: str) -> None:
        """Reproject and align raster to match reference raster."""
        #open the raster to be aligned
        with rasterio.open(src_path) as src:
            src_transform = src.transform
            #open the reference raster/ raster with target dimensions and resolution
            with rasterio.open(ref_path) as ref:
                dst_crs = ref.crs
                dst_transform, dst_width, dst_height = calculate_default_transform(
                    src.crs,    
                    dst_crs,    
                    ref.width,   
                    ref.height,  
                    *ref.bounds,
                )
                dst_kwargs = src.meta.copy()
                dst_kwargs.update({
                                "crs": dst_crs,
                                "transform": dst_transform,
                                "width": dst_width,
                                "height": dst_height,
                                "nodata": 0,
                                "dtype": src.meta["dtype"],})
                #write the aligned raster
                with rasterio.open(dest_path, 'w', **dst_kwargs) as dst:
                    for i in range(1, src.count + 1):
                        reproject(
                            source=rasterio.band(src, i),
                            destination=rasterio.band(dst, i),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=dst_transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest#nearest resampling avoids overstretching rasters, esp given we are moving from 10m to around 3m
                        )

        self.logger.info(f"Coregistered: {os.path.basename(src_path)} to {dest_path}")
    
    def _stack_features(self, year):
        '''
        Stack all feature rasters to be used in prediction for a given year.
        Aligns unaligned rasters once and only adds aligned ones to the stack.
        '''
        features = []
        names = []
        ref_raster = os.path.join(self.masks, '2025_mndwi_watermask_down.tif')

        for file in os.listdir(self.features):
            if not file.lower().endswith('.tif'):
                continue

            filepath = os.path.join(self.features, file)
            basename, _ = os.path.splitext(file)

            # Skip already aligned files for alignment
            if not basename.endswith('_aligned'):
                aligned_path = os.path.join(self.features, f"{basename}_aligned.tif")
                if not os.path.exists(aligned_path):
                    self._coregister_raster(filepath, aligned_path, ref_raster)
                else:
                    self.logger.info(f"Aligned file already exists: {aligned_path}")
            
            # Now only process aligned files
            if basename.endswith('_aligned'):
                # DEM features — static (no year in filename)
                if not any(str(y) in basename for y in range(1900, 2100)):
                    arr, profile = self._load_raster(filepath)
                    features.append(arr)
                    names.append(basename)
                    self.logger.info(f"Added DEM feature: {file}")
                
                # Year-specific features — dynamic
                elif str(year) in basename:
                    arr, profile = self._load_raster(filepath)
                    features.append(arr)
                    names.append(basename)
                    self.logger.info(f"Added time-based feature: {file}")

        if not features:
            raise ValueError(f'No features found for year: {year} in {self.features}')
        
        stacked = np.stack(features)
        self.logger.info(f"Stacked {len(features)} features for {year}: {names}")
        return stacked, profile


    
    def train(self, years: list):
        '''
        Train the model using the features and labels so that it can be used to run prediction
        '''
        X = []
        y = []
        # self._distance_from_shoreline([2007, 2013, 2019, 2025])
        for year in years:
            features, _ = self._stack_features(year)
            labels_path = os.path.join(self.masks, f"{year}_mndwi_watermask_down.tif")
            
            if not os.path.exists(labels_path):
                self.logger.warning(f"No label found for {year}, skipping")
                continue
            
            with rasterio.open(labels_path) as src:
                labels = src.read(1, masked=True)
                
            # Flatten features and labels
            f_2d = features.reshape(features.shape[0], -1).T
            l_1d = labels.flatten()
            
            valid_mask = ~np.any(np.isnan(f_2d), axis=1)
            X.append(f_2d[valid_mask])
            y.append(l_1d[valid_mask])
            # Optional check for fundamental size mismatch
            if l_1d.shape[0] != f_2d.shape[0]:
                self.logger.error(f"Shape mismatch: Features={f_2d.shape[0]}, Labels={l_1d.shape[0]}")
                continue # Skip this year if shapes are fundamentally mismatched
            
        X = np.vstack(X)
        y = np.hstack(y)
        
        # Ensure labels are integers for classification models
        y = y.astype(int)
        unique, counts = np.unique(y, return_counts=True)
        self.logger.info(f"Label Counts: {dict(zip(unique, counts))}")
        self.logger.info(f"Class 0 Percentage: {counts[0]/y.size * 100:.2f}%")
      


        self.logger.info(f"Training dataset size: {X.shape}, labels: {np.unique(y)}")
        self.model.fit(X, y)
        self.logger.info("Model training complete.")
        
    def predict(self, year, save=True):
        """
        Predict flood extent for a target year using trained model.
        """
        features, profile = self._stack_features(year)
        f_2d = features.reshape(features.shape[0], -1).T

        valid_mask = ~np.any(np.isnan(f_2d), axis=1)
        preds = np.zeros(f_2d.shape[0])
        preds[:] = np.nan

        preds[valid_mask] = self.model.predict(f_2d[valid_mask])

        pred_img = preds.reshape(features.shape[1], features.shape[2])

        if save:
            output_path = os.path.join(self.results, f"prediction_{year}.tif")
            profile.update(dtype=rasterio.float32, count=1)
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(pred_img.astype(np.float32), 1)
            self.logger.info(f"Saved prediction to {output_path}")

        return pred_img

    def save_model(self):
        model_path = os.path.join(self.processed, 'model')
        joblib.dump(self.model, model_path)
        self.logger.info(f"Model saved to {model_path}")
        