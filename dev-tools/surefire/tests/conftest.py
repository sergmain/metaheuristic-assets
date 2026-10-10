import os
import sys

# run_test.py sits one level up; conftest is imported before the test modules, which is what makes their import work.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
