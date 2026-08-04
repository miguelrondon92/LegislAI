#!/usr/bin/env python3
"""
Test script to verify intelligent chunking and rate limiting
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

def test_intelligent_chunking():
    """Test intelligent chunking and rate limiting"""
    try:
        with app.app_context():
            logger.info("Testing Intelligent Chunking and Rate Limiting")
            
            # Create AI analyzer
            analyzer = EnhancedAIAnalyzer()
            
            # Test rate limit status
            logger.info("Testing rate limit status...")
            status = analyzer.get_rate_limit_status()
            logger.info(f"Rate limit status: {status}")
            
            # Test token estimation
            test_text = "This is a test text to estimate tokens."
            estimated_tokens = analyzer._estimate_tokens(test_text)
            logger.info(f"Text: '{test_text}'")
            logger.info(f"Estimated tokens: {estimated_tokens}")
            
            # Test optimal chunk size calculation
            logger.info("Testing optimal chunk size calculation...")
            test_lengths = [10000, 50000, 100000, 500000, 1000000]
            
            for length in test_lengths:
                optimal_size = analyzer._calculate_optimal_chunk_size(length)
                estimated_chunks = length // optimal_size
                logger.info(f"Text length: {length:,} chars -> Optimal chunk size: {optimal_size:,} chars -> ~{estimated_chunks} chunks")
            
            # Test with a real bill
            bill = db.session.query(Bill).filter(
                Bill.ai_analysis.is_(None)
            ).first()
            
            if bill:
                logger.info(f"Testing with real bill: {bill.get_bill_identifier()}")
                
                # Get bill text
                from services.congress_api import CongressAPI
                congress_api = CongressAPI()
                full_text = congress_api.get_bill_text(bill.congress, bill.bill_type, bill.bill_number)
                
                if full_text:
                    logger.info(f"Bill text length: {len(full_text):,} characters")
                    
                    # Test chunking
                    text_length = len(full_text)
                    optimal_chunk_size = analyzer._calculate_optimal_chunk_size(text_length)
                    
                    # Update chunker
                    analyzer.bill_chunker.max_chunk_size = optimal_chunk_size
                    
                    # Create chunks
                    chunks = analyzer.bill_chunker.chunk_bill(full_text, bill.title, bill.summary)
                    logger.info(f"Created {len(chunks)} chunks")
                    
                    # Test chunk limiting
                    if len(chunks) > analyzer.max_chunks_per_bill:
                        logger.info(f"Limiting chunks from {len(chunks)} to {analyzer.max_chunks_per_bill}")
                        chunks.sort(key=lambda x: x.importance_score, reverse=True)
                        chunks = chunks[:analyzer.max_chunks_per_bill]
                    
                    # Estimate total tokens
                    total_tokens = sum(analyzer._estimate_tokens(chunk.content) for chunk in chunks)
                    logger.info(f"Total estimated tokens: {total_tokens:,}")
                    
                    # Test rate limit simulation
                    logger.info("Testing rate limit simulation...")
                    for i in range(20):
                        analyzer._record_request()
                        status = analyzer.get_rate_limit_status()
                        if status['is_at_limit']:
                            logger.info(f"Rate limit hit after {i+1} requests")
                            break
                        time.sleep(0.1)  # Small delay for testing
                    
                    # Reset counters
                    analyzer.reset_rate_limit_counters()
                    logger.info("✅ Rate limit counters reset")
                    
                else:
                    logger.warning("No full text available for testing")
            else:
                logger.warning("No bills without AI analysis found for testing")
            
            # Test workflow orchestrator integration
            logger.info("Testing workflow orchestrator integration...")
            orchestrator = WorkflowOrchestrator()
            
            # Get workflow status with rate limiting info
            workflow_status = orchestrator.get_workflow_status()
            logger.info(f"Workflow rate limiting: {workflow_status['rate_limiting']}")
            
            logger.info("✅ Intelligent chunking and rate limiting test completed")
            
    except Exception as e:
        logger.error(f"Error testing intelligent chunking: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_intelligent_chunking() 