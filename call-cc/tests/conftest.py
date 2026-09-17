import os
import sys

# The core under test lives in the payload dir; these tests deliberately do not, so that nothing
# test-shaped is copied onto a Processor when the payload ships (section 4.4 of
# MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md). conftest is imported before the test modules, which is
# what makes the import in them work.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'payload', 'fn-call-cc', 'src'))
