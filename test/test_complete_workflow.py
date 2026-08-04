#!/usr/bin/env python3
"""
Complete workflow test on a single bill
Tests intelligent chunking, rate limiting, AI analysis, and category mapping
"""

import os
import sys
import logging
import time
from datetime import datetime

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill, BillCategoryMapping, PolicyCategory
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.workflow_orchestrator import WorkflowOrchestrator
from services.congress_api import CongressAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_complete_workflow():
    """Test the complete workflow on a single bill"""
    try:
        with app.app_context():
            logger.info("🚀 Starting Complete Workflow Test on Single Bill")
            logger.info("=" * 60)
            
            # Step 1: Find a bill without AI analysis
            logger.info("Step 1: Finding bill without AI analysis...")
            bill = db.session.query(Bill).filter(
                Bill.ai_analysis.is_(None)
            ).first()
            
            if not bill:
                logger.error("❌ No bills without AI analysis found")
                return
            
            logger.info(f"✅ Found bill: {bill.get_bill_identifier()} - {bill.title[:50]}...")
            
            # Step 2: Check initial state
            logger.info("\nStep 2: Checking initial state...")
            initial_analysis = bill.get_ai_analysis()
            initial_categories = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).count()
            
            logger.info(f"📊 Initial AI analysis: {'Present' if initial_analysis else 'None'}")
            logger.info(f"📊 Initial category mappings: {initial_categories}")
            
            # Step 3: Create AI analyzer and check quota
            logger.info("\nStep 3: Setting up AI analyzer...")
            analyzer = EnhancedAIAnalyzer()
            
            # Reset rate limit counters for clean test
            analyzer.reset_rate_limit_counters()
            
            quota_info = analyzer.get_quota_info()
            logger.info(f"📊 AI Quota Status:")
            logger.info(f"   • Requests this minute: {quota_info['current_usage']['requests_this_minute']}")
            logger.info(f"   • Max requests per minute: {quota_info['current_usage']['max_requests_per_minute']}")
            logger.info(f"   • Safe remaining requests: {quota_info['current_usage']['safe_remaining_requests']}")
            logger.info(f"   • Can handle large bill: {quota_info['status']['can_handle_large_bill']}")
            
            # Step 4: Fetch full text
            logger.info("\nStep 4: Fetching full text from Congress API...")
            congress_api = CongressAPI()
            full_text = congress_api.get_bill_text(bill.congress, bill.bill_type, bill.bill_number)
            
            if not full_text:
                logger.warning("⚠️ No full text available, using summary for testing")
                full_text = bill.summary or "Test bill content for analysis"
            
            logger.info(f"📏 Text length: {len(full_text):,} characters")
            
            # Step 5: Test intelligent chunking
            logger.info("\nStep 5: Testing intelligent chunking...")
            text_length = len(full_text)
            optimal_chunk_size = analyzer._calculate_optimal_chunk_size(text_length)
            
            logger.info(f"🎯 Optimal chunk size: {optimal_chunk_size:,} characters")
            logger.info(f"📊 Estimated chunks: {text_length // optimal_chunk_size}")
            
            # Update chunker with optimal size
            analyzer.bill_chunker.max_chunk_size = optimal_chunk_size
            
            # Create chunks
            chunks = analyzer.bill_chunker.chunk_bill(full_text, bill.title, bill.summary)
            logger.info(f"✅ Created {len(chunks)} chunks")
            
            # Test chunk limiting
            if len(chunks) > analyzer.max_chunks_per_bill:
                logger.info(f"⚠️ Limiting chunks from {len(chunks)} to {analyzer.max_chunks_per_bill}")
                chunks.sort(key=lambda x: x.importance_score, reverse=True)
                chunks = chunks[:analyzer.max_chunks_per_bill]
                logger.info(f"📊 Using top {len(chunks)} most important chunks")
            
            # Step 6: Estimate analysis requirements
            logger.info("\nStep 6: Estimating analysis requirements...")
            estimated_requests = analyzer._estimate_analysis_requests(chunks)
            total_estimated_tokens = sum(analyzer._estimate_tokens(chunk.content) for chunk in chunks)
            
            logger.info(f"📊 Estimated API requests: {estimated_requests}")
            logger.info(f"📊 Total estimated tokens: {total_estimated_tokens:,}")
            
            # Check if we can handle this analysis
            can_handle = analyzer._can_handle_analysis(estimated_requests)
            logger.info(f"📊 Can handle analysis: {can_handle}")
            
            if not can_handle:
                logger.warning("⚠️ Insufficient quota for analysis, but continuing for testing...")
            
            # Step 7: Perform AI analysis
            logger.info("\nStep 7: Performing AI analysis...")
            start_time = time.time()
            
            analysis_result = analyzer.analyze_bill(full_text, bill.title)
            
            analysis_time = time.time() - start_time
            logger.info(f"⏱️ Analysis completed in {analysis_time:.2f} seconds")
            
            if analysis_result:
                logger.info("✅ AI analysis completed successfully")
                logger.info(f"📊 Analysis components: {list(analysis_result.keys())}")
                
                # Log analysis details
                if 'summary' in analysis_result:
                    logger.info(f"📝 Summary generated: {len(analysis_result['summary'].get('main_summary', ''))} chars")
                
                if 'policy_implications' in analysis_result:
                    categories = analysis_result['policy_implications'].get('categories', [])
                    logger.info(f"🎯 Policy categories identified: {len(categories)}")
                    for cat in categories[:3]:  # Show first 3
                        logger.info(f"   • {cat.get('area', 'Unknown')} ({cat.get('impact_level', 'Unknown')})")
                
                if 'overall_risk_score' in analysis_result:
                    risk_score = analysis_result['overall_risk_score']
                    logger.info(f"⚠️ Overall risk score: {risk_score:.2f}")
                
                if 'chunks_analyzed' in analysis_result:
                    logger.info(f"🔧 Chunks analyzed: {analysis_result['chunks_analyzed']}")
                
            else:
                logger.error("❌ AI analysis failed")
                return
            
            # Step 8: Store analysis in database
            logger.info("\nStep 8: Storing analysis in database...")
            bill.set_ai_analysis(analysis_result)
            db.session.commit()
            
            logger.info("✅ Analysis stored in database")
            
            # Step 9: Test category mapping
            logger.info("\nStep 9: Testing category mapping...")
            if 'policy_implications' in analysis_result:
                policy_data = analysis_result['policy_implications']
                categories = policy_data.get('categories', [])
                
                if categories:
                    logger.info(f"📊 Processing {len(categories)} policy categories...")
                    
                    # Create workflow orchestrator for category mapping
                    orchestrator = WorkflowOrchestrator()
                    
                    # Store policy categories
                    orchestrator._store_policy_categories(bill, categories, analysis_result)
                    
                    # Check results
                    final_categories = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).count()
                    logger.info(f"✅ Category mappings created: {final_categories}")
                    
                    # Show category details
                    mappings = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).all()
                    for mapping in mappings:
                        category = db.session.query(PolicyCategory).get(mapping.policy_category_id)
                        if category:
                            logger.info(f"   • {category.name} (score: {mapping.relevance_score:.2f}, sneakiness: {mapping.sneakiness_score:.2f})")
                else:
                    logger.warning("⚠️ No policy categories found in analysis")
            else:
                logger.warning("⚠️ No policy implications in analysis")
            
            # Step 10: Check final state
            logger.info("\nStep 10: Checking final state...")
            final_analysis = bill.get_ai_analysis()
            final_categories = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).count()
            
            logger.info(f"📊 Final AI analysis: {'Present' if final_analysis else 'None'}")
            logger.info(f"📊 Final category mappings: {final_categories}")
            
            # Step 11: Check rate limit status
            logger.info("\nStep 11: Checking rate limit status...")
            final_quota_info = analyzer.get_quota_info()
            logger.info(f"📊 Final AI Quota Status:")
            logger.info(f"   • Requests used: {final_quota_info['current_usage']['requests_this_minute']}")
            logger.info(f"   • Remaining requests: {final_quota_info['current_usage']['remaining_requests']}")
            logger.info(f"   • Rate limit percentage: {final_quota_info['current_usage']['percentage_used']:.1f}%")
            
            # Step 12: Test workflow orchestrator integration
            logger.info("\nStep 12: Testing workflow orchestrator integration...")
            workflow_status = orchestrator.get_workflow_status()
            
            logger.info(f"📊 Workflow Rate Limiting:")
            logger.info(f"   • Status: {workflow_status['rate_limiting']['status']}")
            logger.info(f"   • Rate limit hits: {workflow_status['rate_limiting']['rate_limit_hits']}")
            
            if workflow_status['rate_limiting']['ai_quota_info']:
                ai_status = workflow_status['rate_limiting']['ai_quota_info']
                logger.info(f"   • AI analyzer status: {ai_status['status']['is_at_limit']}")
                logger.info(f"   • Can handle large bill: {ai_status['status']['can_handle_large_bill']}")
            
            # Summary
            logger.info("\n" + "=" * 60)
            logger.info("🎉 COMPLETE WORKFLOW TEST SUMMARY")
            logger.info("=" * 60)
            logger.info(f"✅ Bill processed: {bill.get_bill_identifier()}")
            logger.info(f"✅ AI analysis: {'SUCCESS' if final_analysis else 'FAILED'}")
            logger.info(f"✅ Category mappings: {final_categories} created")
            logger.info(f"✅ Rate limits: {'RESPECTED' if final_quota_info['current_usage']['percentage_used'] < 100 else 'EXCEEDED'}")
            logger.info(f"✅ Processing time: {analysis_time:.2f} seconds")
            logger.info(f"✅ Chunks processed: {len(chunks)}")
            logger.info(f"✅ API requests used: {final_quota_info['current_usage']['requests_this_minute']}")
            
            if final_analysis and final_categories > 0:
                logger.info("🎯 RESULT: Complete workflow test PASSED!")
            else:
                logger.warning("⚠️ RESULT: Complete workflow test had issues")
            
    except Exception as e:
        logger.error(f"❌ Error in complete workflow test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_complete_workflow() 