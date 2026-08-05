#!/usr/bin/env python3
"""
Script to check Gemini API quota and rate limits.

Probes the configured GEMINI_MODEL. Never prints the API key.
"""

import os
import sys
import time
import logging

# Allow running from repo root or scripts/debug/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from google.generativeai import genai

from utils.constants import GEMINI_MODEL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_gemini_quota():
    """Check Gemini API quota by making test calls against GEMINI_MODEL."""

    # Get API key (never log its value)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment")
        return

    # Configure the API
    genai.configure(api_key=api_key)

    model_name = GEMINI_MODEL
    model = genai.GenerativeModel(model_name)

    logger.info("Testing Gemini API quota limits...")
    logger.info(f"Model under test: {model_name}")

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

                time.sleep(0.5)

            except Exception as e:
                error_str = str(e)
                if (
                    "429" in error_str
                    or "RESOURCE_EXHAUSTED" in error_str
                    or "quota" in error_str.lower()
                ):
                    rate_limited_calls += 1
                    logger.error(f"🚫 Call {i+1} rate limited: {error_str}")
                    break
                else:
                    other_errors += 1
                    logger.error(f"❌ Call {i+1} failed: {error_str}")

    except KeyboardInterrupt:
        logger.info("Testing interrupted by user")

    logger.info("\n" + "=" * 50)
    logger.info("GEMINI API QUOTA TEST RESULTS")
    logger.info("=" * 50)
    logger.info(f"✅ Successful calls: {successful_calls}")
    logger.info(f"🚫 Rate limited calls: {rate_limited_calls}")
    logger.info(f"❌ Other errors: {other_errors}")
    logger.info(
        f"📊 Total calls attempted: {successful_calls + rate_limited_calls + other_errors}"
    )

    if rate_limited_calls > 0:
        logger.info(f"🎯 Rate limit hit after {successful_calls} successful calls")
        logger.info("💡 Hit RPM and/or daily RPD free-tier quota (API 429 RESOURCE_EXHAUSTED)")
    else:
        logger.info("✅ No rate limits hit in this test")

    logger.info("\n📋 FREE-TIER QUOTA (Google AI Studio, typical):")
    logger.info("• RPM: ~15–30 requests per minute (varies by model/version)")
    logger.info("• RPD: ~1,500 requests per day per project")
    logger.info("• Daily reset: midnight Pacific Time")
    logger.info("• Over limit: HTTP 429 RESOURCE_EXHAUSTED")
    logger.info("• Local app limiter uses 15 RPM (conservative floor of the free-tier band)")
    logger.info(f"• Model probed: {model_name}")
    logger.info("• Privacy: free-tier prompts/responses may be used to improve Google products")


if __name__ == "__main__":
    check_gemini_quota()
