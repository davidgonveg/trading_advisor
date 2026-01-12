import sys
import subprocess
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scripts.full_deploy")

def run_script(module_name):
    logger.info(f"🚀 Starting {module_name}...")
    try:
        # Run module using python -m
        subprocess.check_call([sys.executable, "-m", module_name])
        logger.info(f"✅ {module_name} completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {module_name} failed: {e}")
        sys.exit(1)

def main():
    logger.info("🔧 STARTING FULL DATA DEPLOYMENT")
    
    # 1. Backfill Data
    run_script("scripts.backfill_data")
    
    # 2. Calculate Indicators
    run_script("scripts.calculate_history")
    
    logger.info("🏁 FULL DEPLOYMENT COMPLETE")

if __name__ == "__main__":
    main()
