#!/usr/bin/env python3
"""
Test script to verify limit enforcement and tracking
"""

import os
import sys
import logging
import time
from datetime import datetime

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.workflow_orchestrator import WorkflowOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_limit_enforcement():
    """Test that the system never exceeds API rate limits"""
    try:
        with app.app_context():
            logger.info("Testing Limit Enforcement and Tracking")
            
            # Create AI analyzer
            analyzer = EnhancedAIAnalyzer()
            
            # Test 1: Initial state
            logger.info("Test 1: Initial state")
            quota_info = analyzer.get_quota_info()
            logger.info(f"Initial quota: {quota_info['current_usage']}")
            assert quota_info['current_usage']['requests_this_minute'] == 0, "Should start with 0 requests"
            
            # Test 2: Request tracking
            logger.info("Test 2: Request tracking")
            for i in range(5):
                success = analyzer._record_request()
                assert success, f"Request {i+1} should be recorded successfully"
                status = analyzer.get_rate_limit_status()
                logger.info(f"After request {i+1}: {status['requests_this_minute']}/{status['max_requests_per_minute']}")
            
            # Test 3: Rate limit checking
            logger.info("Test 3: Rate limit checking")
            at_limit = analyzer._check_rate_limit()
            logger.info(f"At limit after 5 requests: {at_limit}")
            assert not at_limit, "Should not be at limit after 5 requests"
            
            # Test 4: Approaching limit
            logger.info("Test 4: Approaching limit")
            # Add more requests to get close to limit
            for i in range(10):  # Total 15 requests (at limit)
                success = analyzer._record_request()
                if not success:
                    logger.info(f"Request {i+6} blocked at limit")
                    break
            
            at_limit = analyzer._check_rate_limit()
            logger.info(f"At limit after 15 requests: {at_limit}")
            assert at_limit, "Should be at limit after 15 requests"
            
            # Test 5: Safety checks
            logger.info("Test 5: Safety checks")
            # Try to record another request when at limit
            success = analyzer._record_request()
            assert not success, "Should not be able to record request when at limit"
            
            # Test 6: Token estimation
            logger.info("Test 6: Token estimation")
            test_texts = [
                "Short text",
                "This is a longer text that should have more tokens",
                "A" * 1000,  # 1000 character text
                "A" * 10000  # 10000 character text
            ]
            
            for text in test_texts:
                tokens = analyzer._estimate_tokens(text)
                logger.info(f"Text length: {len(text)}, Estimated tokens: {tokens}")
                assert tokens > 0, "Token estimation should be positive"
            
            # Test 7: Chunk size calculation
            logger.info("Test 7: Chunk size calculation")
            test_lengths = [10000, 50000, 100000, 500000]
            
            for length in test_lengths:
                optimal_size = analyzer._calculate_optimal_chunk_size(length)
                estimated_chunks = length // optimal_size
                logger.info(f"Text length: {length:,} -> Chunk size: {optimal_size:,} -> ~{estimated_chunks} chunks")
                assert optimal_size >= 1000, "Chunk size should be at least 1000"
                assert optimal_size <= 8000, "Chunk size should be at most 8000"
                assert estimated_chunks <= analyzer.max_chunks_per_bill, f"Should not exceed {analyzer.max_chunks_per_bill} chunks"
            
            # Test 8: Analysis request estimation
            logger.info("Test 8: Analysis request estimation")
            from utils.bill_chunker import BillChunk
            
            # Create test chunks
            test_chunks = [
                BillChunk(content="Test chunk 1", chunk_type="section", importance_score=0.8),
                BillChunk(content="Test chunk 2", chunk_type="section", importance_score=0.7),
                BillChunk(content="Test chunk 3", chunk_type="section", importance_score=0.6),
            ]
            
            estimated_requests = analyzer._estimate_analysis_requests(test_chunks)
            logger.info(f"Estimated requests for {len(test_chunks)} chunks: {estimated_requests}")
            assert estimated_requests > 0, "Should estimate positive number of requests"
            
            # Test 9: Can handle analysis check
            logger.info("Test 9: Can handle analysis check")
            # Reset counters for this test
            analyzer.reset_rate_limit_counters()
            
            can_handle = analyzer._can_handle_analysis(5)
            logger.info(f"Can handle 5 requests: {can_handle}")
            assert can_handle, "Should be able to handle 5 requests with fresh quota"
            
            # Add some requests
            for i in range(10):
                analyzer._record_request()
            
            can_handle = analyzer._can_handle_analysis(10)
            logger.info(f"Can handle 10 requests after using 10: {can_handle}")
            assert not can_handle, "Should not be able to handle 10 requests after using 10"
            
            # Test 10: Workflow integration
            logger.info("Test 10: Workflow integration")
            orchestrator = WorkflowOrchestrator()
            
            # Get workflow status
            workflow_status = orchestrator.get_workflow_status()
            logger.info(f"Workflow rate limiting: {workflow_status['rate_limiting']}")
            
            # Test 11: Reset functionality
            logger.info("Test 11: Reset functionality")
            analyzer.reset_rate_limit_counters()
            
            quota_info = analyzer.get_quota_info()
            logger.info(f"After reset: {quota_info['current_usage']}")
            assert quota_info['current_usage']['requests_this_minute'] == 0, "Should reset to 0 requests"
            
            logger.info("✅ All limit enforcement tests passed!")
            
    except Exception as e:
        logger.error(f"Error testing limit enforcement: {e}")
        import traceback
        traceback.print_exc()

def test_edge_cases():
    """Test edge cases and boundary conditions"""
    try:
        logger.info("Testing Edge Cases")
        
        analyzer = EnhancedAIAnalyzer()
        
        # Test 1: Very large text
        large_text = "A" * 1000000  # 1 million characters
        tokens = analyzer._estimate_tokens(large_text)
        logger.info(f"Large text tokens: {tokens:,}")
        
        # Test 2: Empty text
        empty_tokens = analyzer._estimate_tokens("")
        logger.info(f"Empty text tokens: {empty_tokens}")
        assert empty_tokens == 0, "Empty text should have 0 tokens"
        
        # Test 3: Boundary chunk sizes
        boundary_sizes = [999, 1000, 8000, 8001]
        for size in boundary_sizes:
            optimal = analyzer._calculate_optimal_chunk_size(size)
            logger.info(f"Boundary size {size}: optimal {optimal}")
        
        # Test 4: Rate limit timing
        logger.info("Testing rate limit timing...")
        analyzer.reset_rate_limit_counters()
        
        # Simulate time passing
        analyzer.minute_start_time = time.time() - 30  # 30 seconds ago
        
        # Add some requests
        for i in range(5):
            analyzer._record_request()
        
        status = analyzer.get_rate_limit_status()
        logger.info(f"Status after 30 seconds: {status['requests_this_minute']} requests")
        
        # Simulate minute passing
        analyzer.minute_start_time = time.time() - 65  # 65 seconds ago (should reset)
        
        status = analyzer.get_rate_limit_status()
        logger.info(f"Status after 65 seconds: {status['requests_this_minute']} requests")
        assert status['requests_this_minute'] == 0, "Should reset after minute passes"
        
        logger.info("✅ All edge case tests passed!")
        
    except Exception as e:
        logger.error(f"Error testing edge cases: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_limit_enforcement()
    test_edge_cases() 