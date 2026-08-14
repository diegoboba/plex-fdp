# main.py - Entry point for Cloud Functions
# Cloud Functions requires the entry point function in the root module.
#
# In Cloud Functions deployment, functions_framework is always available,
# so the decorated functions will be defined and importable.
# This file is not used when running locally.

try:
    from src.main_streaming import streaming_etl_scheduled_function, streaming_etl_cloud_function
except ImportError:
    # Running locally without functions_framework — these aren't needed
    pass
