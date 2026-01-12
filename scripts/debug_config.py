
import sys
import os
print(f"CWD: {os.getcwd()}")
print(f"Path: {sys.path}")
try:
    import config
    print(f"Config imported: {config}")
    print(f"Config file: {getattr(config, '__file__', 'No file')}")
    import config.settings
    print("Config.settings imported OK")
except Exception as e:
    print(f"Error: {e}")
