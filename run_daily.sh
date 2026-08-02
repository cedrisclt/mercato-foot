#!/bin/bash
# Lance le scraping + la génération du site, appelé chaque nuit par launchd.
set -e
cd "$(dirname "$0")"
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 scrape.py
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 site/build.py
