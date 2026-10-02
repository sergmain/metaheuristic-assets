import os
import sys

# The core under test lives in the payload dir; these tests deliberately do not, so that nothing test-shaped is
# copied onto a Processor when the payload ships (MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 4.4). conftest is
# imported before the test modules, which is what makes the imports in them work.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'payload', 'fn-mh-api-probe', 'src'))
