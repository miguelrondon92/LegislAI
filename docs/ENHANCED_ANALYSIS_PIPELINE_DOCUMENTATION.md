# Enhanced Legislative Analysis Pipeline Documentation

## Current architecture (2026-08) — start here

Authoritative agent contract: [`.cursor/resources/pipeline-contract.md`](../.cursor/resources/pipeline-contract.md) and [`AGENTS.md`](../AGENTS.md).

| Stage | Behavior |
|-------|----------|
| **Tier A** | `single_pass_full_text` — bills ≤ ~150k tokens; ~2 Gemini calls (core summary/categories + integrity). Sets `display_ready` inputs. |
| **Tier B** | `map_reduce_macro_chunks` — oversized bills; resume via `analyzed_chunk_keys`; UI waves use `allow_budget_waits=False`. |
| **Enrichers** | `services/analysis_enrichers.py` — async **stakeholders** + deep **policy_analysis** after core; RPM-gated via `enrichment_quota_ok()`. Does not block `display_ready`. |
| **UI** | `templates/bill_analysis.html` — **Policy Areas** (badges) separate from **Policy Analysis** (narrative); Stakeholder card uses `affected_groups` / `winners_losers`. |
| **Ops** | `continuation_*` for Tier B resume; `enrichment_queued` / `enrichment_finished` for enrichers; `limit_cause` = `local_minute_budget` \| `gemini_api_429`. |

Historical sections below describe earlier multi-pipeline / hidden-provision work; prefer the contract + `enhanced_ai_analyzer.py` / `analysis_enrichers.py` when they disagree.

---

## Overview

The LegislAI system implements a comprehensive architecture for processing congressional bills with advanced AI analysis capabilities. This documentation covers enhanced analysis features including hidden provision detection, sneakiness scoring, and comprehensive risk assessment.

## System Architecture

### Three Analysis Pipelines

The system provides three equivalent analysis pipelines that all generate identical comprehensive analysis:

1. **Bill Search Pipeline** - Real-time analysis during user searches
2. **Workflow Orchestrator** - Automated processing of new bills via RSS feeds
3. **Backfill Orchestrator** - Bulk processing of historical congressional data

All pipelines utilize the same `EnhancedAIAnalyzer` to ensure consistency and comprehensive analysis coverage.

## Enhanced Analysis Components

### 1. Hidden Provisions Detection

The system implements sophisticated hidden provision detection to identify potentially concerning or "sneaky" content in legislation.

#### Pattern-Based Detection
- **26+ Suspicious Patterns**: Regex patterns for identifying concerning language
  - `notwithstanding any other provision of law`
  - `emergency authority`
  - `bypass normal procedures`
  - `discretionary power`
  - `waiver of requirements`
  - And 21+ additional patterns

#### AI-Powered Analysis
- **Chunk-based Analysis**: Bills are intelligently chunked for comprehensive coverage
- **Cross-chunk Detection**: Identifies hidden provisions spanning multiple sections
- **Risk Assessment**: Categorizes provisions as low/medium/high risk with confidence scores

#### Sneakiness Scoring
- **Per-Category Scoring**: Calculates sneakiness scores for each policy category
- **Database Storage**: Stores sneakiness scores in `BillCategoryMapping.sneakiness_score`
- **Risk Calculation**: `risk_value * confidence_score` for each detected provision

### 2. Comprehensive Risk Assessment

#### Overall Risk Score Calculation
Weighted combination of multiple risk factors:
- **Hidden Provisions**: 40% weight
- **Anomaly Detection**: 20% weight  
- **Suspicious Language**: 20% weight
- **Controversy Score**: 10% weight
- **Complexity Score**: 10% weight

#### Risk Components
- **Hidden Impact Assessment**: Multi-dimensional impact analysis
- **Anomaly Detection**: Structural and content anomalies
- **Cross-Reference Analysis**: Analysis of references to other laws
- **Suspicious Language Detection**: AI + regex pattern matching

### 3. Enhanced Database Structure

#### New Tables
- **AIAnalysis**: Stores comprehensive analysis with versioning
- **Summary**: Enhanced summaries with multiple formats and versioning
- **BillCategoryMapping**: Enhanced with `sneakiness_score` field

#### Legacy Compatibility
- Maintains backward compatibility with existing `bill.ai_analysis` field
- Supports both old and new database structures simultaneously

## Pipeline Implementation Details

### Bill Search Pipeline (`routes.py`)

#### Enhanced Analysis Function
```python
def _perform_analysis_if_needed(bill):
    """Perform comprehensive AI analysis - equivalent to workflow orchestrator"""
    # Check both old and new analysis structures
    has_old_analysis = bool(bill.ai_analysis)
    has_new_analysis = bool(bill.get_active_ai_analysis())
    
    if not has_old_analysis and not has_new_analysis:
        # Perform comprehensive analysis using EnhancedAIAnalyzer
        analysis = ai_analyzer.analyze_bill(bill, bill.title)
        
        # Store policy categories with sneakiness scoring
        if 'policy_implications' in analysis:
            _store_policy_categories_with_sneakiness(bill, categories, analysis)
```

#### Key Features
- ✅ Real-time comprehensive analysis during user searches
- ✅ Enhanced logging with processing metrics
- ✅ Sneakiness scoring per policy category
- ✅ Complete database structure creation

### Workflow Orchestrator (`services/workflow_orchestrator.py`)

#### Core Analysis Method
```python
def _perform_ai_analysis(self, bill: Bill) -> tuple[bool, Optional[Dict]]:
    """Perform AI analysis with hidden provision detection"""
    analysis = self.ai_analyzer.analyze_bill(full_text, bill.title)
    
    # Store policy categories with sneakiness scoring
    if 'policy_implications' in analysis:
        self._store_policy_categories(bill, policy_data['categories'], analysis)
```

#### Enhanced Features
- ✅ RSS-driven automated bill discovery
- ✅ Rate limiting and quota management
- ✅ Comprehensive analysis logging
- ✅ Hidden provision detection and sneakiness mapping

### Backfill Orchestrator (`services/backfill_orchestrator.py`)

#### Enhanced Processing Method
```python
def _process_single_bill(self, bill_info: Dict) -> bool:
    """Process bill with comprehensive analysis - equivalent to workflow orchestrator"""
    # Perform comprehensive analysis using EnhancedAIAnalyzer
    analysis = self.ai_analyzer.analyze_bill(bill, bill.title)
    
    # Store policy categories with sneakiness scoring
    if categories:
        self._create_category_mappings_with_sneakiness(bill, categories, analysis)
```

#### Key Capabilities
- ✅ Bulk processing of historical data
- ✅ Gap analysis and missing bill identification
- ✅ Same comprehensive analysis as other pipelines
- ✅ Persistent state management for resumability

## Enhanced AI Analyzer (`services/enhanced_ai_analyzer.py`)

### Core Analysis Components

#### 1. Hidden Provision Detection
```python
def _detect_hidden_provisions(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
    """Detect potentially hidden or sneaky provisions in bill chunks"""
    # Analyze each chunk for hidden provisions
    # Cross-reference analysis between chunks
    # Calculate overall hidden risk score
```

#### 2. Anomaly Detection
```python
def _detect_anomalies(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
    """Detect structural and content anomalies"""
    # Identify unusual bill structure
    # Detect content patterns that deviate from norms
```

#### 3. Suspicious Language Detection
```python
def _detect_suspicious_language(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
    """Context-aware suspicious language detection"""
    # Pattern-based detection using 26+ patterns
    # AI-powered analysis for concerning language
```

#### 4. Risk Score Calculation
```python
def _calculate_overall_risk_score(self, analysis_results: Dict) -> float:
    """Calculate overall risk score combining all analysis components"""
    # Weighted combination of all risk factors
    # Hidden provisions: 40%, Anomalies: 20%, Suspicious language: 20%, etc.
```

### Analysis Output Structure

#### Comprehensive Analysis Results
```json
{
  "summary": {
    "main_summary": "Bill summary text",
    "key_provisions": ["list", "of", "provisions"],
    "plain_language_explanation": "Simplified explanation"
  },
  "policy_implications": {
    "primary_category": "policy_area",
    "secondary_categories": ["area1", "area2"],
    "category_breakdown": {
      "category_name": {
        "relevance_score": 0.8,
        "reasoning": "Why this category is relevant"
      }
    },
    "overall_assessment": "Comprehensive policy assessment"
  },
  "hidden_provisions": {
    "detected_provisions": [
      {
        "text": "Provision text",
        "type": "emergency_authority",
        "risk_level": "high",
        "confidence_score": 0.85
      }
    ],
    "overall_hidden_risk_score": 0.65
  },
  "stakeholders": {
    "beneficiaries": ["group1", "group2"],
    "negatively_affected": ["group3"],
    "industry_stakeholders": ["industry1"]
  },
  "complexity_assessment": {
    "complexity_score": 0.75
  },
  "controversy_score": 0.45,
  "overall_risk_score": 0.58,
  "generated_at": "2025-07-10T12:00:00",
  "analysis_method": "enhanced_chunked_with_hidden_detection"
}
```

## Database Schema Enhancements

### BillCategoryMapping Enhancements
```sql
ALTER TABLE bill_category_mapping 
ADD COLUMN sneakiness_score REAL DEFAULT 0.0;
```

#### Sneakiness Score Calculation
- **Risk Value Mapping**: 
  - Low risk: 0.2
  - Medium risk: 0.5  
  - High risk: 0.8
- **Final Score**: `risk_value * confidence_score`
- **Category Assignment**: Matches hidden provision text to policy categories

### New Database Tables

#### AIAnalysis Table
- `analysis_data`: JSON field with comprehensive analysis
- `complexity_score`: Extracted complexity metric
- `controversy_score`: Extracted controversy metric
- `analysis_method`: Method used for analysis
- `processing_time`: Time taken for analysis
- `created_at`: Timestamp with versioning support

#### Summary Table
- `summary_text`: Main summary content
- `plain_language_summary`: Simplified explanation
- `key_provisions`: JSON array of key provisions
- `summary_type`: Type of summary (ai_generated, manual, etc.)
- `created_at`: Timestamp with versioning support

## Frontend Integration

### Template Updates (`templates/bill_analysis.html`)

#### Policy Analysis Display
```html
<!-- Enhanced Policy Analysis Section -->
{% if policy.primary_category %}
<div class="col-md-6">
    <h6>Primary Policy Area</h6>
    <span class="badge bg-primary fs-6">{{ policy.primary_category.title() }}</span>
</div>
{% endif %}

{% if policy.category_breakdown %}
<div class="table-responsive">
    <table class="table table-sm">
        <thead>
            <tr>
                <th>Policy Area</th>
                <th>Relevance Score</th>
                <th>Reasoning</th>
            </tr>
        </thead>
        <tbody>
            {% for category_name, category_data in policy.category_breakdown.items() %}
            <tr>
                <td>{{ category_name.title() }}</td>
                <td>
                    {% set score = category_data.relevance_score %}
                    <span class="badge bg-{{ 'success' if score >= 0.7 else 'warning' if score >= 0.4 else 'secondary' }}">
                        {{ "%.1f"|format(score * 100) }}%
                    </span>
                </td>
                <td>{{ category_data.reasoning }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endif %}
```

#### Field Name Compatibility
- ✅ `primary_category` vs `primary_policy_area` support
- ✅ `secondary_categories` vs `secondary_areas` support
- ✅ `category_breakdown` vs `categories` support
- ✅ Enhanced overall assessment display

## Performance and Rate Limiting

### API Quota Management
- **Rate Limiting**: 15 requests per minute (Gemini free tier)
- **Chunked Processing**: Intelligent chunking to stay within limits
- **Backoff Strategy**: Exponential backoff with jitter
- **Quota Monitoring**: Real-time quota tracking and warnings

### Processing Optimization
- **Chunk Size Calculation**: Dynamic chunk sizing based on text length
- **Token Estimation**: Conservative token counting for API limits
- **Batch Processing**: Efficient batch processing for backfill operations
- **Error Recovery**: Robust error handling with graceful degradation

## Security and Privacy

### Data Protection
- **No Sensitive Data Storage**: No API keys stored in analysis results
- **Secure Processing**: All analysis performed server-side
- **Privacy Compliance**: No personal data in analysis outputs

### Error Handling
- **Null Safety**: Comprehensive null checks throughout analysis pipeline
- **Graceful Degradation**: System continues operating if analysis components fail
- **Error Logging**: Detailed error logging for debugging and monitoring

## Monitoring and Logging

### Comprehensive Logging
```python
# Enhanced Analysis Logging
logger.info(f"✅ Enhanced AI analysis completed for: {bill.get_bill_identifier()}")
logger.info(f"  📊 Method: {analysis_method}")
logger.info(f"  🔧 Chunks analyzed: {chunks_analyzed}")
logger.info(f"  📝 Text processed: {text_length:,} characters")
logger.info(f"  ⏱️ Processing time: {processing_time:.2f} seconds")
logger.info(f"  🕵️ Hidden provisions: {provisions_count} detected, risk: {risk_score:.2f}")
logger.info(f"  🧮 Complexity score: {complexity_score:.2f}")
logger.info(f"  ⚡ Controversy score: {controversy_score:.2f}")
logger.info(f"  🚨 Overall risk score: {risk_score:.2f}")
```

### Performance Metrics
- **Processing Speed**: Characters per second processing rate
- **Analysis Coverage**: Number of chunks analyzed per bill
- **Success Rates**: Analysis completion rates across pipelines
- **Error Tracking**: Categorized error logging for troubleshooting

## Deployment and Configuration

### Environment Variables
```bash
# Required API Keys
GEMINI_API_KEY=your_gemini_api_key
CONGRESS_API_KEY=your_congress_api_key

# Optional Configuration
MAX_CHUNKS_PER_BILL=15
MAX_REQUESTS_PER_MINUTE=15
ANALYSIS_TIMEOUT_SECONDS=120
```

### Flask Configuration
- **Database URI**: SQLite with migration support
- **Session Management**: Secure session handling
- **Error Handling**: Custom error pages and logging

## Testing and Validation

### Pipeline Testing
- ✅ **Bill Search Pipeline**: Real-time analysis validation
- ✅ **Workflow Orchestrator**: Automated processing verification  
- ✅ **Backfill Orchestrator**: Bulk processing validation
- ✅ **Database Integration**: New table structure verification
- ✅ **Frontend Display**: Template rendering validation

### Analysis Quality Assurance
- ✅ **Hidden Provision Detection**: Pattern matching validation
- ✅ **Sneakiness Scoring**: Risk calculation verification
- ✅ **Risk Assessment**: Multi-factor scoring validation
- ✅ **Database Consistency**: Cross-pipeline equivalency testing

## Troubleshooting

### Common Issues

#### Analysis Not Generating
- **Check API Keys**: Verify GEMINI_API_KEY is set correctly
- **Rate Limiting**: Check if API quota is exceeded
- **Database Permissions**: Verify database write permissions

#### Missing Sneakiness Scores
- **Hidden Provisions**: Verify hidden provision detection is running
- **Category Mapping**: Check BillCategoryMapping table structure
- **Analysis Pipeline**: Ensure comprehensive analysis is being called

#### Frontend Display Issues
- **Template Fields**: Verify field name compatibility in templates
- **Analysis Structure**: Check if analysis data matches expected format
- **Database Queries**: Verify bill and analysis retrieval queries

### Debug Mode
```python
# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)

# Check analysis pipeline status
with app.app_context():
    bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=1).first()
    analysis = bill.get_ai_analysis()
    print(f"Analysis keys: {list(analysis.keys()) if analysis else 'None'}")
```

## Future Enhancements

### Potential Improvements
- **Real-time Monitoring Dashboard**: Live analysis pipeline monitoring
- **Advanced Caching**: Analysis result caching for performance
- **ML Model Integration**: Custom trained models for legislative analysis
- **Enhanced Visualization**: Interactive risk assessment displays

### Scalability Considerations
- **Database Optimization**: Indexing and query optimization
- **API Rate Management**: More sophisticated quota management
- **Distributed Processing**: Multi-instance processing capabilities
- **Performance Monitoring**: Advanced metrics and alerting

## Conclusion

The Enhanced Legislative Analysis Pipeline provides comprehensive, consistent analysis across all processing methods. With sophisticated hidden provision detection, sneakiness scoring, and multi-factor risk assessment, the system delivers advanced insights into congressional legislation while maintaining performance and reliability.

All three pipelines (Bill Search, Workflow Orchestrator, Backfill Orchestrator) now generate equivalent comprehensive analysis, ensuring consistent quality regardless of how bills are processed in the system.