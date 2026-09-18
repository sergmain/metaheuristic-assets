import os
import sys

# The code under test lives in the payload dir; these tests deliberately do not, so that nothing test-shaped is
# copied onto a Processor when the payload ships (section 4.4 of MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'payload', 'fn-rg-requirements', 'src'))
