import sys
import os

# Ensure the backend directory is on the path so `from auth.jwt import ...` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
