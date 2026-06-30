#!/usr/bin/env bash
# exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Install system dependencies for PDF generation
apt-get update && apt-get install -y --no-install-recommends wkhtmltopdf