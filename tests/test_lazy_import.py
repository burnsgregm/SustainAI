import sys
import unittest.mock
import pytest

def test_lazy_tensorflow_import():
    """Verify that core modules can be imported even if tensorflow fails to initialize."""
    
    # Mock tensorflow as entirely unimportable (like a broken DLL case)
    with unittest.mock.patch.dict(sys.modules, {"tensorflow": None}):
        
        # 1. API should load cleanly
        import sustainai.api
        
        # 2. Predictor module should load cleanly
        import sustainai.predict
        
        # 3. Harness should load cleanly
        import sustainai.harness.evaluate
        
        # Since these executed successfully, we know we don't have top-level TF imports!
        assert True
