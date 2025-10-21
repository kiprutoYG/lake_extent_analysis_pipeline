import os 
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Config:
    #---------------------------------------------------------------------------------------------------------------------------#
    #  GENERAL SETTINGS
    #---------------------------------------------------------------------------------------------------------------------------#
    project_name: str = "LakeExtentAnalysis"
    author: str = "Kosonei Kipruto Elkana"
    
    # --------------------------------------------------------------------------
    # Base directories
    # --------------------------------------------------------------------------
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    data_dir: Path = field(init=False)
    raw_data_dir: Path = field(init=False)
    processed_data_dir: Path = field(init=False)
    results_dir: Path = field(init=False)

    # --------------------------------------------------------------------------
    # Analysis area
    # --------------------------------------------------------------------------
    aoi_path: str = field(init=False)
    target_crs: str = "EPSG:32636"  # UTM Zone 36N

    # --------------------------------------------------------------------------
    # Remote sensing data
    # --------------------------------------------------------------------------
    stac_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    sentinel_collection: str = "sentinel-2-l2a"
    landsat_collection: str = "landsat-c2-l2"
    dem_collection: str = "cop-dem-glo-30"

    cloud_cover_threshold: int = 30

    green_band: str = "B3"
    swir_band: str = "B11"
    target_crs: str = 'EPSG:32636'
    threshold: float = 0.1
    

    # --------------------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------------------
    log_level: str = "INFO"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    project_name: str = "Lake_Baringo_Rise"
    output_prefix: str = field(init=False)

    def __post_init__(self):
        # Initialize dependent paths
        self.data_dir = self.base_dir / "data"
        self.raw_data_dir = self.data_dir / "raw"
        self.processed_data_dir = self.data_dir / "processed"
        self.results_dir = self.data_dir / "results"

        self.aoi_path = os.path.join(self.processed_data_dir, "aoi.shp")
        self.output_prefix = f"{self.project_name}_{self.timestamp}"

        # Temporal ranges — can still be dynamic
        self.date_ranges = [
            ("2007-10-01", "2007-10-31"),
            ("2016-10-01", "2016-10-31"),
            ("2025-09-15", "2025-10-11"),
        ]