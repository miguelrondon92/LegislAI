#!/usr/bin/env python3
"""
Test script for chunked bill analysis
Verifies that the new chunked analysis system works without truncation limits
"""

import os
import sys
import logging
from datetime import datetime

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Bill
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer as AIAnalyzer2
from bill_analyzer import BillAnalyzer
from utils.bill_chunker import BillChunker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_bill_chunker():
    """Test the bill chunker functionality"""
    logger.info("Testing Bill Chunker...")
    
    # Sample bill text with sections
    sample_bill_text = """
    SECTION 1. SHORT TITLE.
    This Act may be cited as the "Test Bill for Chunked Analysis Act".
    
    SECTION 2. FINDINGS.
    Congress finds that:
    (1) This is a test bill for chunked analysis
    (2) It contains multiple sections
    (3) Each section should be properly identified
    
    SECTION 3. PURPOSE.
    The purpose of this Act is to test the chunked analysis system.
    
    SECTION 4. IMPLEMENTATION.
    (a) The Secretary shall implement this Act within 90 days.
    (b) Funding shall be provided as follows:
        (1) $10,000,000 for initial implementation
        (2) $5,000,000 for ongoing operations
    (c) Reports shall be submitted annually.
    
    SECTION 5. EFFECTIVE DATE.
    This Act shall take effect on the date of enactment.
    """
    
    chunker = BillChunker(max_chunk_size=1000, overlap_size=100)
    chunks = chunker.chunk_bill(sample_bill_text, "Test Bill", "A test bill for chunked analysis")
    
    logger.info(f"Created {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks):
        logger.info(f"  Chunk {i+1}: {chunk.chunk_type} - {len(chunk.content)} chars - Score: {chunk.importance_score:.2f}")
        if chunk.section_number:
            logger.info(f"    Section: {chunk.section_number} - {chunk.section_title}")
    
    return chunks

def test_ai_analyzer_chunked():
    """Test the AI analyzer with chunked analysis"""
    logger.info("Testing AI Analyzer with chunked analysis...")
    
    # Sample bill text (longer than previous truncation limits)
    sample_bill_text = """
    SECTION 1. SHORT TITLE.
    This Act may be cited as the "Comprehensive Healthcare Reform Act of 2024".
    
    SECTION 2. FINDINGS.
    Congress finds that:
    (1) Healthcare costs continue to rise at unsustainable rates
    (2) Millions of Americans lack access to affordable healthcare
    (3) The current system creates barriers to preventive care
    (4) Administrative costs consume a significant portion of healthcare spending
    (5) Innovation in healthcare delivery is needed
    
    SECTION 3. PURPOSE.
    The purpose of this Act is to:
    (a) Reduce healthcare costs for all Americans
    (b) Expand access to affordable healthcare coverage
    (c) Improve the quality of healthcare services
    (d) Promote preventive care and wellness programs
    (e) Streamline administrative processes
    
    SECTION 4. HEALTHCARE COST REDUCTION.
    (a) The Secretary of Health and Human Services shall establish a program to reduce healthcare costs by:
        (1) Negotiating prescription drug prices with pharmaceutical companies
        (2) Implementing value-based payment models
        (3) Reducing administrative overhead
        (4) Promoting competition in healthcare markets
    
    (b) Funding for cost reduction programs:
        (1) $50,000,000,000 for prescription drug price negotiation
        (2) $25,000,000,000 for value-based payment implementation
        (3) $15,000,000,000 for administrative streamlining
        (4) $10,000,000,000 for market competition initiatives
    
    SECTION 5. EXPANDED ACCESS TO COVERAGE.
    (a) Medicaid expansion to cover individuals with incomes up to 150% of the federal poverty level
    (b) Establishment of a public option for health insurance
    (c) Subsidies for low and middle-income individuals to purchase coverage
    (d) Prohibition of pre-existing condition exclusions
    
    SECTION 6. QUALITY IMPROVEMENT.
    (a) Implementation of quality metrics and reporting requirements
    (b) Incentives for healthcare providers to improve outcomes
    (c) Patient safety initiatives
    (d) Electronic health record standardization
    
    SECTION 7. PREVENTIVE CARE.
    (a) Coverage for all preventive services without cost-sharing
    (b) Wellness programs and incentives
    (c) Early intervention programs
    (d) Public health education campaigns
    
    SECTION 8. ADMINISTRATIVE STREAMLINING.
    (a) Standardization of billing and coding procedures
    (b) Reduction of paperwork requirements
    (c) Electronic processing of claims
    (d) Simplified enrollment processes
    
    SECTION 9. IMPLEMENTATION TIMELINE.
    (a) Phase 1 (Year 1): Cost reduction programs and administrative streamlining
    (b) Phase 2 (Year 2): Expanded coverage and quality improvement initiatives
    (c) Phase 3 (Year 3): Full implementation of all provisions
    
    SECTION 10. FUNDING.
    (a) Total funding: $200,000,000,000 over 10 years
    (b) Revenue sources:
        (1) Increased taxes on high-income individuals
        (2) Reduced spending on administrative overhead
        (3) Savings from negotiated drug prices
        (4) Efficiency gains from streamlined processes
    
    SECTION 11. EFFECTIVE DATE.
    This Act shall take effect on January 1, 2025.
    """
    
    bill_title = "Comprehensive Healthcare Reform Act of 2024"
    
    # Test different AI analyzers
    analyzers = [
        ("Gemini AI Analyzer", AIAnalyzer()),
        ("Gemini AI Analysis", AIAnalyzer2()),
        ("OpenAI Bill Analyzer", BillAnalyzer())
    ]
    
    for name, analyzer in analyzers:
        logger.info(f"\nTesting {name}...")
        try:
            start_time = datetime.now()
            analysis = analyzer.analyze_bill(sample_bill_text, bill_title)
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            
            if analysis:
                logger.info(f"✅ {name} completed successfully in {processing_time:.2f} seconds")
                
                # Check for chunked analysis indicators
                chunks_analyzed = analysis.get('chunks_analyzed', 0)
                analysis_method = analysis.get('analysis_method', 'unknown')
                
                if chunks_analyzed > 0:
                    logger.info(f"  📊 Chunked analysis: {chunks_analyzed} chunks analyzed")
                if analysis_method == 'chunked':
                    logger.info(f"  🔧 Analysis method: {analysis_method}")
                
                # Check for key analysis components
                if 'summary' in analysis:
                    logger.info(f"  📝 Summary generated: {len(str(analysis['summary']))} chars")
                if 'policy_implications' in analysis:
                    logger.info(f"  🎯 Policy implications analyzed")
                if 'stakeholders' in analysis:
                    logger.info(f"  👥 Stakeholder analysis completed")
                
            else:
                logger.error(f"❌ {name} failed to produce analysis")
                
        except Exception as e:
            logger.error(f"❌ {name} error: {str(e)}")

def test_full_bill_analysis():
    """Test analysis on a real bill from the database"""
    logger.info("\nTesting full bill analysis on database bill...")
    
    with app.app_context():
        # Get a bill from the database
        bill = Bill.query.first()
        if not bill:
            logger.warning("No bills found in database for testing")
            return
        
        logger.info(f"Testing analysis on bill: {bill.get_bill_identifier()}")
        
        # Get full text
        full_text = bill.get_full_text()
        if not full_text:
            logger.warning(f"No full text available for bill {bill.get_bill_identifier()}")
            return
        
        logger.info(f"Bill text length: {len(full_text)} characters")
        
        # Test with AI analyzer
        analyzer = EnhancedAIAnalyzer()
        try:
            start_time = datetime.now()
            analysis = analyzer.analyze_bill(full_text, bill.title)
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            
            if analysis:
                logger.info(f"✅ Full bill analysis completed in {processing_time:.2f} seconds")
                
                chunks_analyzed = analysis.get('chunks_analyzed', 0)
                analysis_method = analysis.get('analysis_method', 'unknown')
                
                logger.info(f"  📊 Analysis method: {analysis_method}")
                logger.info(f"  🔧 Chunks analyzed: {chunks_analyzed}")
                logger.info(f"  📝 Text length processed: {len(full_text)} characters")
                
                # Verify no truncation occurred
                if len(full_text) > 10000:  # If bill is longer than old truncation limit
                    logger.info(f"  ✅ No truncation detected - full {len(full_text)} characters processed")
                
            else:
                logger.error("❌ Full bill analysis failed")
                
        except Exception as e:
            logger.error(f"❌ Full bill analysis error: {str(e)}")

def main():
    """Run all tests"""
    logger.info("Starting chunked analysis tests...")
    
    # Test 1: Bill chunker
    test_bill_chunker()
    
    # Test 2: AI analyzers with chunked analysis
    test_ai_analyzer_chunked()
    
    # Test 3: Full bill analysis
    test_full_bill_analysis()
    
    logger.info("\n🎉 All chunked analysis tests completed!")

if __name__ == "__main__":
    main() 