#!/bin/bash

# Set the install directory
export APP_DIR=/app/share/flipstack

# Add the app directory to PYTHONPATH so python can find your modules
export PYTHONPATH=$APP_DIR:$PYTHONPATH

# Run the main application
# We use "$@" to pass any arguments through
exec python3 $APP_DIR/main.py "$@"
