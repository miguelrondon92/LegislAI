#!/usr/bin/env python3
"""
Script to check Gemini API quota and rate limits
"""

import os
import time
import logging
from google.generativeai import genai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_gemini_quota():
    """Check Gemini API quota by making test calls"""
    
    # Get API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment")
        return
    
    # Configure the API
    genai.configure(api_key=api_key)
    
    # Test model
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    logger.info("Testing Gemini API quota limits...")
    
    # Make test calls to check limits
    test_prompt = "Hello, this is a test message. Please respond with 'OK'."
    
    successful_calls = 0
    rate_limited_calls = 0
    other_errors = 0
    
    try:
        for i in range(20):  # Test up to 20 calls
            try:
                logger.info(f"Making call {i+1}/20...")
                
                response = model.generate_content(test_prompt)
                
                if response and response.text:
                    successful_calls += 1
                    logger.info(f"✅ Call {i+1} successful: {response.text.strip()}")
                else:
                    other_errors += 1
                    logger.warning(f"⚠️ Call {i+1} returned empty response")
                
                # Small delay between calls
                time.sleep(0.5)
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
                    rate_limited_calls += 1
                    logger.error(f"🚫 Call {i+1} rate limited: {error_str}")
                    break  # Stop testing if we hit rate limit
                else:
                    other_errors += 1
                    logger.error(f"❌ Call {i+1} failed: {error_str}")
    
    except KeyboardInterrupt:
        logger.info("Testing interrupted by user")
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("GEMINI API QUOTA TEST RESULTS")
    logger.info("="*50)
    logger.info(f"✅ Successful calls: {successful_calls}")
    logger.info(f"🚫 Rate limited calls: {rate_limited_calls}")
    logger.info(f"❌ Other errors: {other_errors}")
    logger.info(f"📊 Total calls attempted: {successful_calls + rate_limited_calls + other_errors}")
    
    if rate_limited_calls > 0:
        logger.info(f"🎯 Rate limit hit after {successful_calls} successful calls")
        logger.info("💡 This suggests the per-minute or per-hour quota limit")
    else:
        logger.info("✅ No rate limits hit in this test")
    
    # Check for quota information in responses
    logger.info("\n📋 QUOTA INFORMATION:")
    logger.info("• Free tier: ~15 requests per minute")
    logger.info("• Paid tier: Higher limits based on billing")
    logger.info("• Quota resets: Every minute (rate limits)")
    logger.info("• Daily limits: Varies by billing plan")
    logger.info("• Model: gemini-2.0-flash (used in this test)")

if __name__ == "__main__":
    check_gemini_quota() 