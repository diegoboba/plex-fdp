#!/usr/bin/env python3
"""
Logging helper to capture print statements and save to log files.
Supports Cloud Logging when running in Google Cloud Functions.
"""

import sys
import logging
from datetime import datetime
from io import StringIO
import os


def is_cloud_environment():
    """Detect if running inside Google Cloud Functions / Cloud Run"""
    return os.environ.get('K_SERVICE') is not None or os.environ.get('FUNCTION_TARGET') is not None


def setup_cloud_logging():
    """Initialize Google Cloud Logging integration.

    When running in GCP, this routes all Python logging to Cloud Logging
    with structured JSON format for better filtering in Logs Explorer.
    """
    try:
        import google.cloud.logging
        client = google.cloud.logging.Client()
        client.setup_logging()
        logging.info("Cloud Logging initialized successfully")
    except Exception as e:
        logging.warning(f"Could not initialize Cloud Logging, using default: {e}")


class TeeOutput:
    """Captures print statements and sends them to both console and log file"""
    
    def __init__(self, logger):
        self.logger = logger
        self.terminal = sys.stdout
        
    def write(self, message):
        # Write to terminal (console)
        self.terminal.write(message)
        self.terminal.flush()
        
        # Write to log file (remove newlines for cleaner logging)
        if message.strip():
            # Remove ANSI color codes for cleaner log files
            clean_message = self._remove_ansi_codes(message.strip())
            self.logger.info(clean_message)
    
    def flush(self):
        self.terminal.flush()
    
    def _remove_ansi_codes(self, text):
        """Remove ANSI escape sequences (colors) from text"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)


class ETLLogger:
    """Enhanced ETL logging system"""
    
    def __init__(self, log_prefix="etl"):
        self.log_prefix = log_prefix
        self.logger = None
        self.original_stdout = None
        self.log_filename = None
        
    def setup_logging(self):
        """Setup comprehensive logging system.

        In Cloud environments: uses Cloud Logging (structured JSON).
        Locally: writes to file + console as before.
        """
        if is_cloud_environment():
            setup_cloud_logging()
            logging.basicConfig(level=logging.INFO, force=True)
            self.logger = logging.getLogger('etl_pipeline')
            self.logger.info("ETL Pipeline Started (Cloud)", extra={
                "etl_prefix": self.log_prefix,
            })
            # In cloud, stdout already goes to Cloud Logging — no file/tee needed
            return self.logger

        # --- Local mode: file + console ---
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = f"{log_dir}/{self.log_prefix}_{timestamp}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_filename, encoding='utf-8')
            ],
            force=True
        )

        self.logger = logging.getLogger('etl_pipeline')

        self.logger.info("="*80)
        self.logger.info(f"ETL Pipeline Started - {datetime.now()}")
        self.logger.info(f"Log file: {self.log_filename}")
        self.logger.info("="*80)

        self.original_stdout = sys.stdout
        sys.stdout = TeeOutput(self.logger)

        print(f"Logging to: {self.log_filename}")

        return self.logger
    
    def restore_stdout(self):
        """Restore original stdout"""
        if self.original_stdout:
            sys.stdout = self.original_stdout
    
    def log_completion(self, success=True, error_msg=None):
        """Log pipeline completion"""
        if success:
            self.logger.info(f"ETL Pipeline Completed Successfully - {datetime.now()}")
        else:
            self.logger.error(f"ETL Pipeline Failed - {datetime.now()}")
            if error_msg:
                self.logger.error(f"Error: {error_msg}")

        if self.log_filename:
            print(f"Full log saved to: {self.log_filename}")
    
    def __enter__(self):
        """Context manager entry"""
        self.setup_logging()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is not None:
            self.log_completion(success=False, error_msg=str(exc_val))
        else:
            self.log_completion(success=True)
        self.restore_stdout()