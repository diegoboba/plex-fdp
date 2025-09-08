#!/usr/bin/env python3
"""
Logging helper to capture print statements and save to log files
"""

import sys
import logging
from datetime import datetime
from io import StringIO
import os


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
        """Setup comprehensive logging system"""
        # Create logs directory
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Generate log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = f"{log_dir}/{self.log_prefix}_{timestamp}.log"
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_filename, encoding='utf-8')
            ],
            force=True  # Reset any previous logging configuration
        )
        
        # Create logger
        self.logger = logging.getLogger('etl_pipeline')
        
        # Log the start
        self.logger.info("="*80)
        self.logger.info(f"ETL Pipeline Started - {datetime.now()}")
        self.logger.info(f"Log file: {self.log_filename}")
        self.logger.info("="*80)
        
        # Setup stdout redirection to capture all prints
        self.original_stdout = sys.stdout
        sys.stdout = TeeOutput(self.logger)
        
        print(f"📝 Logging to: {self.log_filename}")
        
        return self.logger
    
    def restore_stdout(self):
        """Restore original stdout"""
        if self.original_stdout:
            sys.stdout = self.original_stdout
    
    def log_completion(self, success=True, error_msg=None):
        """Log pipeline completion"""
        self.logger.info("="*80)
        if success:
            self.logger.info(f"ETL Pipeline Completed Successfully - {datetime.now()}")
        else:
            self.logger.error(f"ETL Pipeline Failed - {datetime.now()}")
            if error_msg:
                self.logger.error(f"Error: {error_msg}")
        self.logger.info("="*80)
        
        print(f"📄 Full log saved to: {self.log_filename}")
    
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