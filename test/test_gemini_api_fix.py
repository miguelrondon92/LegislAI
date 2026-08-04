#!/usr/bin/env python3
"""
Test the Google Generative AI API fix
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

def test_gemini_api_fix():
    """Test that the Gemini API initialization works correctly"""
    logger.info("🧪 Testing Gemini API fix...")
    
    try:
        # Create comprehensive mocks
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_model = mock.MagicMock()
        mock_response = mock.MagicMock()
        
        # Set up the mock chain
        mock_google.generativeai = mock_genai
        mock_genai.configure = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_model.generate_content.return_value = mock_response
        mock_response.text = '{"test": "response"}'
        
        # Mock other dependencies
        mock_bill_chunker = mock.MagicMock()
        
        mocks = {
            'google': mock_google,
            'google.generativeai': mock_genai,
            'utils.constants': mock.MagicMock(),
            'utils.bill_chunker': mock.MagicMock(),
        }
        
        with mock.patch.dict('sys.modules', mocks):
            # Mock the BillChunker class
            with mock.patch('services.enhanced_ai_analyzer.BillChunker') as mock_chunker_class:
                mock_chunker_class.return_value = mock_bill_chunker
                
                # Mock the constants
                with mock.patch('services.enhanced_ai_analyzer.FEDERAL_POLICY_CATEGORIES', ['test_category']):
                    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
                    
                    # Create analyzer with API key
                    with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
                        analyzer = EnhancedAIAnalyzer()
                        
                        # Test that genai.configure was called correctly
                        mock_genai.configure.assert_called_with(api_key='test-key')
                        logger.info("✅ genai.configure called with correct API key")
                        
                        # Test that GenerativeModel was created correctly
                        mock_genai.GenerativeModel.assert_called_with('gemini-1.5-flash')
                        logger.info("✅ GenerativeModel created with correct model name")
                        
                        # Test that the client is the model
                        assert analyzer.client == mock_model
                        logger.info("✅ Analyzer client is the GenerativeModel")
                        
                        # Test that we can call generate_content
                        analyzer.client.generate_content("test prompt")
                        mock_model.generate_content.assert_called_with("test prompt")
                        logger.info("✅ generate_content method is callable")
                        
                        return True
                        
    except Exception as e:
        logger.error(f"❌ Gemini API fix test failed: {e}")
        return False

def test_api_call_pattern():
    """Test that the API call pattern is correct"""
    logger.info("🧪 Testing API call pattern...")
    
    try:
        # Create mocks
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_model = mock.MagicMock()
        mock_response = mock.MagicMock()
        
        # Set up the mock chain
        mock_google.generativeai = mock_genai
        mock_genai.configure = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_model.generate_content.return_value = mock_response
        mock_response.text = '{"analysis": "test"}'
        
        mocks = {
            'google': mock_google,
            'google.generativeai': mock_genai,
            'utils.constants': mock.MagicMock(),
            'utils.bill_chunker': mock.MagicMock(),
        }
        
        with mock.patch.dict('sys.modules', mocks):
            with mock.patch('services.enhanced_ai_analyzer.BillChunker'):
                with mock.patch('services.enhanced_ai_analyzer.FEDERAL_POLICY_CATEGORIES', ['test']):
                    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
                    
                    # Create analyzer with API key
                    with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
                        analyzer = EnhancedAIAnalyzer()
                        
                        # Test that the client can be used for API calls
                        response = analyzer.client.generate_content("test prompt")
                        assert response.text == '{"analysis": "test"}'
                        logger.info("✅ API call pattern works correctly")
                        
                        return True
                        
    except Exception as e:
        logger.error(f"❌ API call pattern test failed: {e}")
        return False

def test_error_handling():
    """Test that error handling still works"""
    logger.info("🧪 Testing error handling...")
    
    try:
        # Create mocks
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_google.generativeai = mock_genai
        
        mocks = {
            'google': mock_google,
            'google.generativeai': mock_genai,
            'utils.constants': mock.MagicMock(),
            'utils.bill_chunker': mock.MagicMock(),
        }
        
        with mock.patch.dict('sys.modules', mocks):
            with mock.patch('services.enhanced_ai_analyzer.BillChunker'):
                with mock.patch('services.enhanced_ai_analyzer.FEDERAL_POLICY_CATEGORIES', ['test']):
                    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
                    
                    # Test initialization without API key
                    with mock.patch.dict(os.environ, {}, clear=True):
                        analyzer = EnhancedAIAnalyzer()
                        
                        # Should handle missing API key gracefully
                        assert analyzer.api_key is None
                        assert analyzer.client is None
                        logger.info("✅ Handles missing API key gracefully")
                        
                        # genai.configure should not be called
                        mock_genai.configure.assert_not_called()
                        logger.info("✅ genai.configure not called without API key")
                        
                        return True
                        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False

def test_deployment_scenario():
    """Test the deployment scenario that was failing"""
    logger.info("🧪 Testing deployment scenario...")
    
    try:
        # Create mocks that simulate the production environment
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_model = mock.MagicMock()
        
        # Set up the mock chain exactly as the new API expects
        mock_google.generativeai = mock_genai
        mock_genai.configure = mock.MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        mocks = {
            'google': mock_google,
            'google.generativeai': mock_genai,
            'utils.constants': mock.MagicMock(),
            'utils.bill_chunker': mock.MagicMock(),
        }
        
        with mock.patch.dict('sys.modules', mocks):
            with mock.patch('services.enhanced_ai_analyzer.BillChunker'):
                with mock.patch('services.enhanced_ai_analyzer.FEDERAL_POLICY_CATEGORIES', ['test']):
                    # This simulates the exact import chain that was failing:
                    # main.py -> app.py -> routes.py -> enhanced_ai_analyzer.py
                    
                    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
                    logger.info("✅ Import successful")
                    
                    # This is what routes.py does: ai_analyzer = EnhancedAIAnalyzer()
                    with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
                        analyzer = EnhancedAIAnalyzer()
                        logger.info("✅ Analyzer initialization successful")
                        
                        # Verify the correct API calls were made
                        mock_genai.configure.assert_called_with(api_key='test-key')
                        mock_genai.GenerativeModel.assert_called_with('gemini-1.5-flash')
                        logger.info("✅ Correct API calls made")
                        
                        return True
                        
    except Exception as e:
        logger.error(f"❌ Deployment scenario test failed: {e}")
        return False

def run_gemini_api_tests():
    """Run all Gemini API tests"""
    logger.info("🚀 Running Gemini API Fix Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Gemini API Fix", test_gemini_api_fix),
        ("API Call Pattern", test_api_call_pattern),
        ("Error Handling", test_error_handling),
        ("Deployment Scenario", test_deployment_scenario)
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
    logger.info("📊 GEMINI API TEST RESULTS:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"   {test_name}: {status}")
    
    logger.info(f"\n🎯 Summary: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All Gemini API tests passed!")
        logger.info("🚀 The API fix should resolve the deployment error.")
        return True
    else:
        logger.error("⚠️ Some Gemini API tests failed.")
        return False

if __name__ == "__main__":
    success = run_gemini_api_tests()
    sys.exit(0 if success else 1)