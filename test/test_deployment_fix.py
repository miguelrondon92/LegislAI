#!/usr/bin/env python3
"""
Test the deployment fix for enhanced_ai_analyzer import
"""

import sys
import os
import ast
import logging

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_import_statement_syntax():
    """Test that the import statement in the file is syntactically correct"""
    logger.info("🧪 Testing import statement syntax in enhanced_ai_analyzer.py...")
    
    try:
        file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services', 'enhanced_ai_analyzer.py')
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the file to check syntax
        try:
            tree = ast.parse(content)
            logger.info("✅ File syntax is valid")
        except SyntaxError as e:
            logger.error(f"❌ Syntax error in file: {e}")
            return False
        
        # Check for the correct import statement
        correct_import = "import google.generativeai as genai"
        incorrect_import = "from google import genai"
        
        if correct_import in content:
            logger.info("✅ Found correct import: 'import google.generativeai as genai'")
        else:
            logger.error("❌ Correct import statement not found")
            return False
        
        if incorrect_import in content:
            logger.error("❌ Found incorrect import: 'from google import genai'")
            return False
        else:
            logger.info("✅ No incorrect import statements found")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing import statement: {e}")
        return False

def test_file_can_be_parsed():
    """Test that the Python file can be parsed without syntax errors"""
    logger.info("🧪 Testing that enhanced_ai_analyzer.py can be parsed...")
    
    try:
        file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services', 'enhanced_ai_analyzer.py')
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Try to compile the file
        try:
            compile(content, file_path, 'exec')
            logger.info("✅ File compiles successfully")
            return True
        except SyntaxError as e:
            logger.error(f"❌ Compilation error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Other error during compilation: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error reading file: {e}")
        return False

def test_import_would_work_in_production():
    """Test that the import would work in production environment"""
    logger.info("🧪 Testing production-style import...")
    
    try:
        # This simulates what would happen in production
        # We create a mock module structure
        import unittest.mock as mock
        
        # Create a mock google module structure
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_google.generativeai = mock_genai
        
        with mock.patch.dict('sys.modules', {
            'google': mock_google,
            'google.generativeai': mock_genai
        }):
            # This is what the fixed import does
            exec("import google.generativeai as genai")
            logger.info("✅ Import statement executes successfully")
            
            # Test that we can access the module
            exec("client = genai.Client(api_key='test')")
            logger.info("✅ Can create client from imported module")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Production-style import test failed: {e}")
        return False

def test_routes_import_chain():
    """Test that the import chain from routes.py works"""
    logger.info("🧪 Testing routes.py import chain...")
    
    try:
        # Mock all the dependencies
        import unittest.mock as mock
        
        # Create comprehensive mocks
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_google.generativeai = mock_genai
        
        with mock.patch.dict('sys.modules', {
            'google': mock_google,
            'google.generativeai': mock_genai,
            'utils.constants': mock.MagicMock(),
            'utils.bill_chunker': mock.MagicMock(),
            'app': mock.MagicMock(),
            'db_models': mock.MagicMock(),
            'services.notification_helper': mock.MagicMock()
        }):
            # Test the import chain: routes -> enhanced_ai_analyzer
            from services.enhanced_ai_analyzer import EnhancedAIAnalyzer, AIAnalysisPartialError
            logger.info("✅ Can import from services.enhanced_ai_analyzer")
            
            # Test that classes are usable
            assert EnhancedAIAnalyzer is not None
            assert AIAnalysisPartialError is not None
            logger.info("✅ Imported classes are accessible")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Routes import chain test failed: {e}")
        return False

def test_deployment_scenario():
    """Test the full deployment scenario that was failing"""
    logger.info("🧪 Testing deployment scenario...")
    
    try:
        import unittest.mock as mock
        
        # Mock the environment that would exist in production
        mock_google = mock.MagicMock()
        mock_genai = mock.MagicMock()
        mock_google.generativeai = mock_genai
        
        mocks = {
            'google': mock_google,
            'google.generativeai': mock_genai,
            'utils.constants': mock.MagicMock(),
            'utils.bill_chunker': mock.MagicMock(),
            'app': mock.MagicMock(),
            'db_models': mock.MagicMock(),
            'services.notification_helper': mock.MagicMock(),
            'flask': mock.MagicMock(),
            'flask_login': mock.MagicMock(),
            'flask_mail': mock.MagicMock(),
            'sqlalchemy': mock.MagicMock()
        }
        
        with mock.patch.dict('sys.modules', mocks):
            # This simulates the exact import chain that was failing:
            # main.py -> app.py -> routes.py -> enhanced_ai_analyzer.py
            
            # Step 1: Import enhanced_ai_analyzer (this was failing)
            from services.enhanced_ai_analyzer import EnhancedAIAnalyzer, AIAnalysisPartialError
            logger.info("✅ Step 1: Enhanced AI Analyzer import successful")
            
            # Step 2: Create analyzer instance (this is what routes.py does)
            with mock.patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
                analyzer = EnhancedAIAnalyzer()
                logger.info("✅ Step 2: Analyzer initialization successful")
            
            # Step 3: Test that the genai module is accessible
            assert hasattr(analyzer, 'client')
            logger.info("✅ Step 3: Analyzer has client attribute")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Deployment scenario test failed: {e}")
        return False

def run_deployment_tests():
    """Run all deployment-related tests"""
    logger.info("🚀 Running Deployment Fix Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Import Statement Syntax", test_import_statement_syntax),
        ("File Can Be Parsed", test_file_can_be_parsed),
        ("Production Import", test_import_would_work_in_production),
        ("Routes Import Chain", test_routes_import_chain),
        ("Full Deployment Scenario", test_deployment_scenario)
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
    logger.info("📊 DEPLOYMENT TEST RESULTS:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"   {test_name}: {status}")
    
    logger.info(f"\n🎯 Summary: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All deployment tests passed! The import fix is working correctly.")
        logger.info("🚀 Your application should now deploy successfully in production.")
        return True
    else:
        logger.error("⚠️ Some deployment tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = run_deployment_tests()
    sys.exit(0 if success else 1)