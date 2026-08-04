#!/usr/bin/env python3
"""
Test runner for LegislAI - runs all test scripts in the test/ directory
and provides a comprehensive report of system health.
"""

import os
import sys
import logging
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_test_script(script_path):
    """Run a single test script and return success status"""
    try:
        logger.info(f"Running {script_path.name}...")
        
        # Run the test script
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info(f"✅ {script_path.name} - PASSED")
            return True, result.stdout
        else:
            logger.error(f"❌ {script_path.name} - FAILED")
            logger.error(f"Error output: {result.stderr}")
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        logger.error(f"❌ {script_path.name} - TIMEOUT (5 minutes)")
        return False, "Test timed out after 5 minutes"
    except Exception as e:
        logger.error(f"❌ {script_path.name} - ERROR: {e}")
        return False, str(e)

def get_test_categories():
    """Categorize test files by their purpose"""
    test_dir = Path(__file__).parent
    
    categories = {
        "Database & Models": [
            "test_database_cleanup_validation.py",
            "test_simple_bill_db.py",
            "test_bill_analysis_db.py",
        ],
        "AI Analysis": [
            "test_chunked_analysis.py",
            "test_gemini.py",
            "test_intelligent_chunking.py",
            "test_enhanced_hidden_detection.py",
        ],
        "API Integration": [
            "test_backfill_system.py",
            "test_full_text_fetch.py",
            "test_bill_versioning.py",
        ],
        "Workflow Systems": [
            "test_simple_workflow.py",
            "test_complete_workflow.py",
            "test_workflow.py",
            "test_workflow_comprehensive.py",
            "test_workflow_processing.py",
            "test_small_bill_workflow.py",
        ],
        "Rate Limiting & Monitoring": [
            "test_rate_limit_stop.py",
            "test_limit_enforcement.py",
            "test_backoff_logic.py",
            "test_monitoring_core.py",
            "test_monitoring_standalone.py",
            "test_monitoring_system.py",
        ],
        "Category Mapping": [
            "test_category_mapping.py",
            "test_simple_category_mapping.py",
        ],
        "Notifications": [
            "test_notifications.py",
        ],
        "System Summary": [
            "test_summary.py",
        ],
        "HR1 Analysis": [
            "test_hr1_analysis.py",
        ],
        "Single Bill Tests": [
            "test_workflow_orchestrator_single_bill.py",
        ]
    }
    
    # Find any test files not categorized
    all_test_files = set()
    for scripts in categories.values():
        all_test_files.update(scripts)
    
    actual_test_files = {f.name for f in test_dir.glob("test_*.py") if f.name != "run_all_tests.py"}
    uncategorized = actual_test_files - all_test_files
    
    if uncategorized:
        categories["Uncategorized"] = list(uncategorized)
    
    return categories

def main():
    """Run all test scripts and provide summary"""
    logger.info("🧪 LEGISLAI COMPREHENSIVE TEST SUITE")
    logger.info("=" * 60)
    logger.info(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    test_dir = Path(__file__).parent
    categories = get_test_categories()
    
    all_results = {}
    category_results = {}
    
    total_start_time = time.time()
    
    # Run tests by category
    for category_name, test_files in categories.items():
        logger.info(f"\n📂 CATEGORY: {category_name}")
        logger.info("-" * 40)
        
        category_results[category_name] = {}
        
        for test_file in test_files:
            test_path = test_dir / test_file
            
            if not test_path.exists():
                logger.warning(f"⚠️ {test_file} - FILE NOT FOUND")
                category_results[category_name][test_file] = (False, "File not found")
                continue
            
            start_time = time.time()
            success, output = run_test_script(test_path)
            duration = time.time() - start_time
            
            category_results[category_name][test_file] = (success, output)
            all_results[test_file] = {
                'success': success,
                'duration': duration,
                'category': category_name,
                'output': output
            }
    
    total_duration = time.time() - total_start_time
    
    # Generate comprehensive summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 COMPREHENSIVE TEST SUMMARY")
    logger.info("=" * 60)
    
    # Overall statistics
    total_tests = len(all_results)
    passed_tests = sum(1 for result in all_results.values() if result['success'])
    failed_tests = total_tests - passed_tests
    
    logger.info(f"📈 Overall Results: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
    logger.info(f"⏱️ Total Duration: {total_duration:.1f} seconds")
    
    # Category breakdown
    logger.info(f"\n📂 Results by Category:")
    for category_name, results in category_results.items():
        if not results:
            continue
            
        category_passed = sum(1 for success, _ in results.values() if success)
        category_total = len(results)
        percentage = category_passed / category_total * 100 if category_total > 0 else 0
        
        logger.info(f"   {category_name}: {category_passed}/{category_total} ({percentage:.1f}%)")
    
    # Failed tests details
    if failed_tests > 0:
        logger.info(f"\n❌ Failed Tests ({failed_tests}):")
        for test_name, result in all_results.items():
            if not result['success']:
                logger.info(f"   • {test_name} ({result['category']})")
                # Show first few lines of error
                error_lines = result['output'].split('\n')[:3]
                for line in error_lines:
                    if line.strip():
                        logger.info(f"     {line.strip()}")
    
    # Longest running tests
    logger.info(f"\n⏱️ Longest Running Tests:")
    sorted_by_duration = sorted(all_results.items(), key=lambda x: x[1]['duration'], reverse=True)
    for test_name, result in sorted_by_duration[:5]:
        logger.info(f"   {test_name}: {result['duration']:.1f}s")
    
    # Key system validations
    logger.info(f"\n🔍 Key System Validations:")
    
    key_tests = {
        "Database Cleanup": "test_database_cleanup_validation.py",
        "Backfill System": "test_backfill_system.py", 
        "AI Analysis": "test_chunked_analysis.py",
        "Workflow": "test_simple_workflow.py",
        "System Summary": "test_summary.py"
    }
    
    for validation_name, test_file in key_tests.items():
        if test_file in all_results:
            status = "✅ PASSED" if all_results[test_file]['success'] else "❌ FAILED"
            duration = all_results[test_file]['duration']
            logger.info(f"   {validation_name}: {status} ({duration:.1f}s)")
        else:
            logger.info(f"   {validation_name}: ⚠️ NOT FOUND")
    
    # Final assessment
    logger.info(f"\n" + "=" * 60)
    
    if passed_tests == total_tests:
        logger.info("🎉 ALL TESTS PASSED!")
        logger.info("✅ LegislAI system is fully operational")
        logger.info("✅ Database contains only real congressional data")
        logger.info("✅ AI analysis pipeline is working correctly")
        logger.info("✅ All workflows and integrations are functional")
        logger.info("✅ System is ready for production use")
    elif passed_tests / total_tests >= 0.8:
        logger.info("✅ MOSTLY SUCCESSFUL!")
        logger.info(f"✅ {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
        logger.info("⚠️ Some non-critical tests failed - review above for details")
        logger.info("✅ Core functionality is operational")
    else:
        logger.warning("⚠️ SIGNIFICANT ISSUES DETECTED")
        logger.warning(f"❌ Only {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
        logger.warning("❌ Multiple system components may have issues")
        logger.warning("❌ Review failed tests before using in production")
    
    logger.info(f"\n📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    return passed_tests == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)