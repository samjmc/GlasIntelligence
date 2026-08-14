"""Logging configuration for the OASIS parallel simulation runner."""

import logging
import os

class MaxTokensWarningFilter(logging.Filter):
    """Filter out camel-ai warnings about max_tokens (we intentionally do not set max_tokens, letting the model decide)"""
    
    def filter(self, record):
        # Filter out log records containing max_tokens warnings
        if "max_tokens" in record.getMessage() and "Invalid or missing" in record.getMessage():
            return False
        return True


# Add the filter immediately at module load so it takes effect before camel code runs
logging.getLogger().addFilter(MaxTokensWarningFilter())


def disable_oasis_logging():
    """
    Disable verbose logging from the OASIS library
    OASIS logging is too verbose (logs every agent observation and action); we use our own action_logger
    """
    # Disable all OASIS loggers
    oasis_loggers = [
        "social.agent",
        "social.twitter", 
        "social.rec",
        "oasis.env",
        "table",
    ]
    
    for logger_name in oasis_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)  # only record critical errors
        logger.handlers.clear()
        logger.propagate = False


def init_logging_for_simulation(simulation_dir: str):
    """
    Initialize logging configuration for the simulation
    
    Args:
        simulation_dir: path to the simulation directory
    """
    # Disable OASIS verbose logging
    disable_oasis_logging()
    
    # Remove the old log directory (if present)
    old_log_dir = os.path.join(simulation_dir, "log")
    if os.path.exists(old_log_dir):
        import shutil
        shutil.rmtree(old_log_dir, ignore_errors=True)
