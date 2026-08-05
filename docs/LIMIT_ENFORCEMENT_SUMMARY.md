# Enhanced Limit Enforcement System

> **2026-08 note:** Size-aware Tier A/B + TPM governor supersede parts of this doc (e.g. “max 15 chunks”, front-of-bill importance bias). For current behavior see `AGENTS.md` and `.cursor/resources/pipeline-contract.md`. Enrichment RPM checks use `enrichment_quota_ok()` → `get_rate_limit_status()["remaining_requests"]`, **not** `get_quota_info()["status"]["safe_remaining_requests"]` (that nest is wrong and caused false skips).

## Overview

The workflow system now includes comprehensive limit enforcement to ensure it **never exceeds** API rate limits. This prevents API abuse, maintains system stability, and provides predictable behavior.

## Key Features

### 1. **Intelligent Chunk Scaling**
- **Automatic chunk size calculation** based on bill length
- **Maximum 15 chunks per bill** to stay within limits
- **Token estimation** to prevent oversized requests
- **Importance-based chunk selection** when limiting is needed

### 2. **Robust Rate Limit Tracking**
- **Per-minute request counting** with automatic reset
- **Safety buffer** (2 requests) to prevent edge cases
- **Real-time quota monitoring** with detailed status
- **Request validation** before recording

### 3. **Pre-Analysis Quota Checking**
- **Request estimation** before starting analysis
- **Quota availability verification** before processing
- **Graceful skipping** when insufficient quota
- **Detailed logging** of quota decisions

### 4. **Multiple Safety Layers**
- **Double-checking** rate limits before each request
- **Request recording validation** with safety checks
- **Workflow-level quota monitoring**
- **Automatic workflow stopping** when limits are hit

## Implementation Details

### Rate Limit Configuration
```python
# Free tier limits
self.max_requests_per_minute = 15
self.max_chunks_per_bill = 15
self.max_tokens_per_request = 30000
self.estimated_tokens_per_char = 0.25  # 1 token ≈ 4 characters
```

### Intelligent Chunking
```python
def _calculate_optimal_chunk_size(self, total_text_length: int) -> int:
    # Target: stay under max_chunks_per_bill and max_tokens_per_request
    max_chars_per_chunk = min(
        self.max_tokens_per_request / self.estimated_tokens_per_char,
        total_text_length / self.max_chunks_per_bill
    )
    
    # Ensure reasonable bounds
    min_chunk_size = 1000
    max_chunk_size = 8000
    
    return max(min_chunk_size, min(max_chunk_size, int(max_chars_per_chunk)))
```

### Request Estimation
```python
def _estimate_analysis_requests(self, chunks: List[BillChunk]) -> int:
    # Each chunk typically needs multiple analysis types
    requests_per_chunk = 5  # Hidden provisions, summary, categories, etc.
    base_requests = len(chunks) * requests_per_chunk
    
    # Add requests for cross-chunk analysis
    cross_chunk_requests = max(1, len(chunks) // 3)
    
    # Add requests for overall analysis
    overall_requests = 3  # Final summary, risk assessment, etc.
    
    return base_requests + cross_chunk_requests + overall_requests
```

### Quota Validation
```python
def _can_handle_analysis(self, estimated_requests: int) -> bool:
    remaining_requests = self.max_requests_per_minute - self.requests_this_minute
    
    # Add safety margin (leave 2 requests buffer)
    safe_remaining = max(0, remaining_requests - 2)
    
    return estimated_requests <= safe_remaining
```

## Safety Mechanisms

### 1. **Request Recording Safety**
```python
def _record_request(self):
    # Safety check - never exceed the limit
    if self.requests_this_minute >= self.max_requests_per_minute:
        logger.error(f"🚫 CRITICAL: Attempted to record request when already at limit!")
        return False
    
    self.requests_this_minute += 1
    return True
```

### 2. **Double-Check Before API Calls**
```python
def _call_ai_model(self, prompt):
    # Double-check rate limit before making request
    if self._check_rate_limit():
        logger.error(f"🚫 Rate limit check failed")
        return None
    
    # Record the request for rate limiting (with safety check)
    if not self._record_request():
        logger.error(f"🚫 Failed to record request due to rate limit")
        return None
    
    # Make API call
    response = self.client.generate_content(prompt)
```

### 3. **Workflow-Level Monitoring**
```python
def _perform_ai_analysis(self, bill: Bill):
    # Check AI analyzer rate limit status with detailed quota info
    quota_info = self.ai_analyzer.get_quota_info()
    
    if quota_info['status']['is_at_limit']:
        self.logger.warning(f"⚠️ AI analyzer at rate limit")
        return False, None
    
    if quota_info['status']['is_approaching_limit']:
        self.logger.warning(f"⚠️ AI analyzer very close to rate limit")
        return False, None
```

## Monitoring and Status

### Detailed Quota Information
```python
def get_quota_info(self) -> Dict:
    return {
        'current_usage': {
            'requests_this_minute': self.requests_this_minute,
            'max_requests_per_minute': self.max_requests_per_minute,
            'remaining_requests': remaining_requests,
            'safe_remaining_requests': safe_remaining,
            'percentage_used': percentage_used
        },
        'limits': {
            'max_chunks_per_bill': self.max_chunks_per_bill,
            'max_tokens_per_request': self.max_tokens_per_request,
            'max_requests_per_minute': self.max_requests_per_minute
        },
        'status': {
            'is_at_limit': is_at_limit,
            'is_approaching_limit': is_approaching_limit,
            'can_handle_large_bill': can_handle_large_bill,
            'can_handle_small_bill': can_handle_small_bill
        }
    }
```

### Workflow Status Integration
```json
{
  "rate_limiting": {
    "rate_limit_hits": 2,
    "workflow_stopped_due_to_rate_limit": false,
    "status": "normal",
    "ai_analyzer_status": {
      "requests_this_minute": 5,
      "max_requests_per_minute": 15,
      "remaining_requests": 10,
      "safe_remaining_requests": 8,
      "is_at_limit": false,
      "is_approaching_limit": false
    },
    "ai_quota_info": {
      "current_usage": {...},
      "limits": {...},
      "status": {...}
    }
  }
}
```

## Benefits

### 1. **API Respect**
- **Never exceeds** rate limits
- **Maintains good standing** with API provider
- **Prevents account suspension**
- **Predictable API usage**

### 2. **System Stability**
- **No unexpected failures** due to rate limits
- **Graceful degradation** when limits are approached
- **Consistent behavior** across different bill sizes
- **Automatic recovery** when quota resets

### 3. **User Experience**
- **Clear logging** of quota decisions
- **Predictable processing** times
- **No surprise failures**
- **Transparent status** information

### 4. **Cost Management**
- **Optimized resource usage**
- **Prevents wasted processing**
- **Efficient chunk sizing**
- **Smart request planning**

## Testing

### Comprehensive Test Suite
- **Limit enforcement verification**
- **Request tracking accuracy**
- **Token estimation validation**
- **Chunk size calculation testing**
- **Edge case handling**
- **Workflow integration testing**

### Test Coverage
- **Boundary conditions** (0 requests, 15 requests)
- **Timing scenarios** (minute boundaries)
- **Large text handling** (1M+ characters)
- **Quota exhaustion** scenarios
- **Reset functionality** verification

## Configuration

### Adjustable Parameters
```python
# Rate limiting
self.max_requests_per_minute = 15  # Free tier
self.max_chunks_per_bill = 15      # Maximum chunks
self.max_tokens_per_request = 30000  # Token limit

# Safety margins
safety_buffer = 2  # Leave 2 requests buffer
approaching_threshold = 0.8  # 80% usage warning
```

### Production Recommendations
- **Monitor usage patterns** and adjust limits accordingly
- **Set up alerts** for approaching limits
- **Consider upgrading** API quota for higher throughput
- **Distribute processing** across time periods

## Conclusion

The enhanced limit enforcement system provides **bulletproof protection** against API rate limit violations while maintaining optimal performance and user experience. The system now:

1. **Never exceeds** API rate limits
2. **Intelligently scales** processing based on available quota
3. **Provides detailed monitoring** and status information
4. **Gracefully handles** quota exhaustion scenarios
5. **Maintains system stability** under all conditions

This ensures sustainable operation and prevents any risk of API abuse or account suspension. 