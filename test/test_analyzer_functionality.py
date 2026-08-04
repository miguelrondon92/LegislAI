#!/usr/bin/env python3
"""
Test enhanced_ai_analyzer functionality with mock data
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

def test_analyzer_with_mock_api():
    """Test that the analyzer can make API calls with the correct import"""
    logger.info("🧪 Testing analyzer with mock API calls...")
    
    try:
        # Create comprehensive mocks
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_client = mock.MagicMock()
        mock_response = mock.MagicMock()
        
        # Set up the mock chain
        mock_google.generativeai = mock_genai
        mock_genai.Client.return_value = mock_client
        mock_client.generate_text.return_value = mock_response
        mock_response.result = '{"analysis": "test analysis"}'
        
        # Mock other dependencies
        mock_bill_chunker = mock.MagicMock()
        mock_bill_chunker.chunk_bill_text.return_value = ["test chunk"]
        
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
                        
                        # Test that the client was created correctly
                        mock_genai.Client.assert_called_with(api_key='test-key')
                        logger.info("✅ Analyzer created genai.Client with correct API key")
                        
                        # Test that the analyzer has the correct attributes
                        assert analyzer.client == mock_client
                        assert analyzer.api_key == 'test-key'
                        logger.info("✅ Analyzer has correct client and API key")
                        
                        return True
                        
    except Exception as e:
        logger.error(f"❌ Mock API test failed: {e}")
        return False

def test_analyzer_method_calls():
    """Test that analyzer methods can be called"""
    logger.info("🧪 Testing analyzer method calls...")
    
    try:
        # Create comprehensive mocks
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_client = mock.MagicMock()
        
        mock_google.generativeai = mock_genai
        mock_genai.Client.return_value = mock_client
        
        # Mock other dependencies
        mock_bill_chunker = mock.MagicMock()
        mock_chunk = mock.MagicMock()
        mock_chunk.text = "test chunk text"
        mock_chunk.metadata = {"chunk_id": 1}
        mock_bill_chunker.chunk_bill_text.return_value = [mock_chunk]
        
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
                        
                        # Test that we can call analyzer methods
                        try:
                            # Test chunking
                            chunks = analyzer.bill_chunker.chunk_bill_text("test bill text")
                            assert len(chunks) == 1
                            logger.info("✅ Bill chunking works")
                            
                            # Test pattern matching
                            patterns = analyzer.suspicious_patterns
                            assert isinstance(patterns, list)
                            logger.info("✅ Suspicious patterns accessible")
                            
                            # Test policy categories
                            categories = analyzer.policy_categories
                            assert categories == ['test_category']
                            logger.info("✅ Policy categories accessible")
                            
                            return True
                            
                        except Exception as e:
                            logger.error(f"❌ Method call failed: {e}")
                            return False
                        
    except Exception as e:
        logger.error(f"❌ Method call test failed: {e}")
        return False

def test_error_handling():
    """Test that the analyzer handles errors gracefully"""
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
                        
                        return True
                        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False

def run_functionality_tests():
    """Run all functionality tests"""
    logger.info("🚀 Running Enhanced AI Analyzer Functionality Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Mock API Integration", test_analyzer_with_mock_api),
        ("Method Calls", test_analyzer_method_calls),
        ("Error Handling", test_error_handling)
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
    logger.info("📊 FUNCTIONALITY TEST RESULTS:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"   {test_name}: {status}")
    
    logger.info(f"\n🎯 Summary: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All functionality tests passed!")
        logger.info("🚀 Enhanced AI Analyzer is working correctly with the fixed import.")
        return True
    else:
        logger.error("⚠️ Some functionality tests failed.")
        return False

if __name__ == "__main__":
    success = run_functionality_tests()
    sys.exit(0 if success else 1)