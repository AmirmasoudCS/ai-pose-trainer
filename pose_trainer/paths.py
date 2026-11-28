"""Folders used by the app. Everything is relative to the project root, so the app
works no matter where the project is stored."""
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGE_DIR)

MODELS_DIR = os.path.join(ROOT_DIR, "models")                   # pose model (downloaded once)
DATA_DIR = os.path.join(ROOT_DIR, "data")                       # created at runtime
PROFILES_PATH = os.path.join(DATA_DIR, "profiles.json")
RESULTS_DIR = os.path.join(DATA_DIR, "results")                 # saved result images
