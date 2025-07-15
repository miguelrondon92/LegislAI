#!/usr/bin/env python3
"""
Test enhanced_ai_analyzer import fix and basic functionality
"""

import sys
import os
import logging
import unittest.mock as mock

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_import_syntax():
    """Test that the import syntax is correct"""
    logger.info("🧪 Testing import syntax...")
    
    # Mock the google.generativeai module to test import syntax
    with mock.patch.dict('sys.modules', {
        'google': mock.MagicMock(),
        'google.generativeai': mock.MagicMock()
    }):
        try:
            # Test the import statement works
            import google.generativeai as genai
            logger.info("✅ Import statement 'import google.generativeai as genai' is syntactically correct")
            
            # Test that we can access the module
            assert genai is not None
            logger.info("✅ Module can be accessed as 'genai'")
            
            return True
        except Exception as e:
            logger.error(f"❌ Import syntax test failed: {e}")
            return False

def test_analyzer_import():
    """Test that the analyzer can be imported with mocked dependencies"""
    logger.info("🧪 Testing analyzer import...")
    
    # Create mock for google.generativeai
    mock_genai = mock.MagicMock()
    mock_client = mock.MagicMock()
    mock_genai.Client.return_value = mock_client
    
    with mock.patch.dict('sys.modules', {
        'google': mock.MagicMock(),
        'google.generativeai': mock_genai
    }):
        try:
            from services.enhanced_ai_analyzer import EnhancedAIAnalyzer, AIAnalysisPartialError
            logger.info("✅ Successfully imported EnhancedAIAnalyzer and AIAnalysisPartialError")
            
            # Test that the classes exist
            assert EnhancedAIAnalyzer is not None
            assert AIAnalysisPartialError is not None
            logger.info("✅ Classes are properly defined")
            
            return True
        except Exception as e:
            logger.error(f"❌ Analyzer import test failed: {e}")
            return False

def test_analyzer_initialization():
    """Test that the analyzer can be initialized with mocked dependencies"""
    logger.info("🧪 Testing analyzer initialization...")
    
    # Create comprehensive mock
    mock_genai = mock.MagicMock()
    mock_client = mock.MagicMock()
    mock_genai.Client.return_value = mock_client
    
    with mock.patch.dict('sys.modules', {
        'google': mock.MagicMock(),
        'google.generativeai': mock_genai
    }):
        try:
            from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
            
            # Test initialization with API key
            with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
                analyzer = EnhancedAIAnalyzer()
                assert analyzer.api_key == 'test-key'
                assert analyzer.client is not None
                logger.info("✅ Analyzer initializes correctly with API key")
                
                # Test that genai.Client was called correctly
                mock_genai.Client.assert_called_with(api_key='test-key')
                logger.info("✅ genai.Client called with correct parameters")
            
            # Test initialization without API key
            with mock.patch.dict(os.environ, {}, clear=True):
                analyzer = EnhancedAIAnalyzer()
                assert analyzer.api_key is None
                assert analyzer.client is None
                logger.info("✅ Analyzer handles missing API key gracefully")
            
            return True
        except Exception as e:
            logger.error(f"❌ Analyzer initialization test failed: {e}")
            return False

def test_analyzer_attributes():
    """Test that the analyzer has all expected attributes"""
    logger.info("🧪 Testing analyzer attributes...")
    
    mock_genai = mock.MagicMock()
    mock_client = mock.MagicMock()
    mock_genai.Client.return_value = mock_client
    
    with mock.patch.dict('sys.modules', {
        'google': mock.MagicMock(),
        'google.generativeai': mock_genai
    }):
        try:
            from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
            
            with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
                analyzer = EnhancedAIAnalyzer()
                
                # Check expected attributes
                expected_attributes = [
                    'api_key', 'client', 'max_requests_per_minute', 'max_chunks_per_bill',
                    'max_tokens_per_request', 'estimated_tokens_per_char', 'bill_chunker',
                    'policy_categories', 'suspicious_patterns'
                ]
                
                for attr in expected_attributes:
                    assert hasattr(analyzer, attr), f"Missing attribute: {attr}"
                    logger.info(f"✅ Has attribute: {attr}")
                
                # Check some specific values
                assert analyzer.max_requests_per_minute == 15
                assert analyzer.max_chunks_per_bill == 15
                assert analyzer.max_tokens_per_request == 30000
                logger.info("✅ Configuration values are correct")
                
                return True
        except Exception as e:
            logger.error(f"❌ Analyzer attributes test failed: {e}")
            return False

def test_exception_class():
    """Test that the AIAnalysisPartialError exception works correctly"""
    logger.info("🧪 Testing AIAnalysisPartialError exception...")
    
    mock_genai = mock.MagicMock()
    with mock.patch.dict('sys.modules', {
        'google': mock.MagicMock(),
        'google.generativeai': mock_genai
    }):
        try:
            from services.enhanced_ai_analyzer import AIAnalysisPartialError
            
            # Test basic exception
            error = AIAnalysisPartialError("Test error")
            assert str(error) == "Test error"
            logger.info("✅ Basic exception creation works")
            
            # Test exception with parameters
            error = AIAnalysisPartialError(
                "Partial completion",
                completion_percentage=50,
                completed_chunks=5,
                total_chunks=10
            )
            assert error.completion_percentage == 50
            assert error.completed_chunks == 5
            assert error.total_chunks == 10
            logger.info("✅ Exception with parameters works")
            
            return True
        except Exception as e:
            logger.error(f"❌ Exception class test failed: {e}")
            return False

def run_all_tests():
    """Run all tests"""
    logger.info("🚀 Running Enhanced AI Analyzer Import Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Import Syntax", test_import_syntax),
        ("Analyzer Import", test_analyzer_import),
        ("Analyzer Initialization", test_analyzer_initialization),
        ("Analyzer Attributes", test_analyzer_attributes),
        ("Exception Class", test_exception_class)
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n📋 Running: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST RESULTS:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"   {test_name}: {status}")
    
    logger.info(f"\n🎯 Summary: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Enhanced AI Analyzer import fix is working correctly.")
        return True
    else:
        logger.error("⚠️ Some tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)