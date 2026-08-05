from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app import app
from db_models import db, Bill, User, Alert, PolicyCategory, UserPolicySubscription, BillCategoryMapping, BillAction, AIAnalysis, Summary, OpsAlert
import logging
import threading
import time as _time_module
from datetime import datetime
from services.congress_api import CongressAPI, APIRateLimitError, get_shared_congress_api
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer, AIAnalysisPartialError
from services.bill_processor import BillProcessor
from utils.constants import GEMINI_MODEL

# Initialize services (shared Congress client for rate-limit spacing)
congress_api = get_shared_congress_api()
ai_analyzer = EnhancedAIAnalyzer()
bill_processor = BillProcessor(congress_api=congress_api, ai_analyzer=ai_analyzer)

# Per-bill in-flight analysis lock (process-local)
_analyzing_bill_ids = set()
_analyzing_lock = threading.Lock()
# Separate lock for downstream enrichments so they don't block core analysis spawn
_enriching_bill_ids = set()
_enriching_lock = threading.Lock()
# After a real RPM deferral, don't re-queue until local minute resets
_enrichment_defer_until = {}
_enrichment_defer_lock = threading.Lock()

# Initialize workflow orchestrator as a global instance
workflow_orchestrator = None

def get_workflow_orchestrator():
    """Get the global workflow orchestrator instance"""
    global workflow_orchestrator
    if workflow_orchestrator is None:
        from services.workflow_orchestrator import WorkflowOrchestrator
        workflow_orchestrator = WorkflowOrchestrator()
    return workflow_orchestrator

@app.route('/')
def index():
    """Main dashboard showing recent bills and user alerts"""
    # Get recent bills - only show latest version of each unique bill
    recent_bills = _get_unique_recent_bills(limit=10)
    
    # Get user alerts if user is authenticated
    alerts = []
    if current_user.is_authenticated:
        alerts = Alert.query.filter_by(user_id=current_user.id, is_read=False)\
                           .order_by(Alert.created_at.desc()).limit(5).all()

    ops_unread_count = OpsAlert.query.filter_by(is_read=False).count()
    ops_unread_preview = OpsAlert.query.filter_by(is_read=False)\
        .order_by(OpsAlert.created_at.desc()).limit(5).all()
    
    return render_template(
        'index.html',
        recent_bills=recent_bills,
        alerts=alerts,
        ops_unread_count=ops_unread_count,
        ops_unread_preview=ops_unread_preview,
    )

@app.route('/bill_search', methods=['GET', 'POST'])
def bill_search():
    """Search for bills using various criteria with enhanced search types"""
    bills = []
    error_message = None
    search_query = ""
    search_type = "bill_number"
    congress = 119  # Default to current congress (119th)
    
    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        search_type = request.form.get('search_type', 'bill_number')
        congress = int(request.form.get('congress', 119))
        
        if search_query:
            try:
                if search_type == 'bill_number':
                    # Search by specific bill number - check database first
                    bill = _get_or_fetch_bill_by_number(search_query, congress)
                    if bill:
                        bills = [bill]
                    else:
                        error_message = f"Bill '{search_query}' not found"
                        
                elif search_type == 'keyword':
                    # Search by keywords - hybrid approach
                    bills = _search_bills_hybrid(search_query, 'keyword', limit=20)
                    if not bills:
                        error_message = f"No bills found matching keywords '{search_query}'"
                        
                elif search_type == 'sponsor':
                    # Search by sponsor name - hybrid approach
                    bills = _search_bills_hybrid(search_query, 'sponsor', limit=20)
                    if not bills:
                        error_message = f"No bills found with sponsor '{search_query}'"
                        
            except APIRateLimitError as e:
                logging.warning(f"Congress API rate limit exceeded during {search_type} search: {str(e)}")
                if search_type == 'bill_number':
                    error_message = f"Unable to fetch bill '{search_query}' from Congress.gov due to API rate limits. If this bill exists in our database, it would appear in search results. Please try again later to search for new bills."
                else:
                    error_message = f"Unable to search for new bills matching '{search_query}' due to API rate limits. Results shown are from our existing database only. Please try again later to include new bills from Congress.gov."
            except AIAnalysisPartialError as e:
                logging.warning(f"AI analysis was partial during {search_type} search: {str(e)}")
                try:
                    from services.ops_alert_service import (
                        PARTIAL_ANALYSIS,
                        notify_gemini_failure,
                    )
                    notify_gemini_failure(
                        PARTIAL_ANALYSIS,
                        str(e),
                        severity="warning",
                        bill_identifier=search_query,
                        completion_percentage=e.completion_percentage,
                        provider_model=getattr(ai_analyzer, 'model_name', None),
                        source="routes",
                        extra={
                            "search_type": search_type,
                            "completed_chunks": e.completed_chunks,
                            "total_chunks": e.total_chunks,
                        },
                    )
                except Exception:
                    pass
                if search_type == 'bill_number':
                    error_message = f"Bill '{search_query}' was found but analysis is only {e.completion_percentage:.1f}% complete due to AI API limits. You can view the partial analysis, or try again later for complete analysis."
                else:
                    # For keyword/sponsor searches, this shouldn't really happen as we only analyze if needed
                    error_message = f"Some bills matching '{search_query}' have incomplete analysis due to AI API limits. You can view available results or try again later."
            except Exception as e:
                logging.error(f"Error in bill search ({search_type}): {str(e)}")
                error_message = "An error occurred while searching for bills. Please try again."
    
    # Check if any bills have background analysis running
    background_analysis_info = None
    if bills:
        partial_bills = []
        for bill in bills:
            analysis = bill.get_active_ai_analysis()
            if analysis:
                data = analysis.get_analysis_data()
                if data and data.get('is_partial', False):
                    completion = data.get('completion_percentage', 0)
                    if completion < 50:
                        partial_bills.append((bill.get_bill_identifier(), completion))
        
        if partial_bills:
            background_analysis_info = {
                'count': len(partial_bills),
                'bills': partial_bills
            }
    
    return render_template('bill_search.html', bills=bills, error_message=error_message, 
                         search_query=search_query, search_type=search_type, congress=congress,
                         background_analysis_info=background_analysis_info)

def _get_or_fetch_bill_by_number(search_query, congress):
    """Get bill by number - check database first, fetch from API if needed"""
    try:
        # Parse the bill identifier to get congress, type, and number
        bill_parts = _parse_bill_identifier(search_query)
        if not bill_parts:
            return None
            
        bill_congress, bill_type, bill_number = bill_parts
        
        # Check if bill exists in database (prioritize display-ready, but include all)
        existing_bill = Bill.query.filter_by(
            congress=bill_congress,
            bill_type=bill_type, 
            bill_number=bill_number
        ).order_by(Bill.display_ready.desc(), Bill.id.desc()).first()
        
        if existing_bill:
            logging.info(f"Found existing bill in database: {existing_bill.get_bill_identifier()}")
            
            # Check if we need to update actions (simple check - could be enhanced)
            if not existing_bill.actions:
                logging.info("No actions found, fetching from API...")
                fetch_bill_actions_from_api(existing_bill)
            
            # Check if we need AI analysis (prioritize new table structure)
            active_analysis = existing_bill.get_active_ai_analysis()
            needs_analysis = False
            
            if not active_analysis and not existing_bill.ai_analysis:
                logging.info("No AI analysis found, performing analysis...")
                needs_analysis = True
            elif active_analysis:
                # Resume Tier B map-reduce partials only (clear stale rows instead of legacy hardcode)
                analysis_data = active_analysis.get_analysis_data()
                if analysis_data and _is_tier_b_partial(analysis_data):
                    completion = analysis_data.get('completion_percentage', 0)
                    if completion < 100:
                        can_analyze = _can_continue_tier_b_wave()
                        if can_analyze:
                            logging.info(
                                f"Partial AI analysis found ({completion:.1f}% complete), "
                                "sufficient quota available, performing continued analysis..."
                            )
                            needs_analysis = True
                        else:
                            logging.info(
                                f"Partial AI analysis found ({completion:.1f}% complete), "
                                "but insufficient API quota remaining. Try again later."
                            )
                    else:
                        logging.info(f"Sufficient AI analysis found ({completion:.1f}% complete)")
                elif analysis_data and analysis_data.get('is_partial'):
                    logging.info(
                        "Non-Tier-B partial on file; skipping auto-resume "
                        f"({analysis_data.get('analysis_method')}) — clear and re-ingest to reanalyze"
                    )
                else:
                    logging.info("Complete AI analysis found")
            
            if needs_analysis:
                # Partial resume needs force_continue so analyze_bill re-runs despite existing AIAnalysis
                force = bool(
                    active_analysis
                    and active_analysis.get_analysis_data()
                    and active_analysis.get_analysis_data().get('is_partial')
                )
                if _analysis_is_in_flight(getattr(existing_bill, "id", None)):
                    logging.info(
                        f"Skipping search resume for {existing_bill.get_bill_identifier()} "
                        "— analysis already in flight"
                    )
                else:
                    if force:
                        try:
                            from services.ops_alert_service import (
                                CONTINUATION_QUEUED,
                                notify_gemini_failure,
                            )
                            adata = active_analysis.get_analysis_data() or {}
                            completion = adata.get('completion_percentage', 0)
                            model_name = getattr(ai_analyzer, 'model_name', GEMINI_MODEL)
                            notify_gemini_failure(
                                CONTINUATION_QUEUED,
                                (
                                    f"Continuation queued from search at {completion:.1f}% "
                                    f"(model={model_name})."
                                ),
                                severity="info",
                                bill=existing_bill,
                                completion_percentage=completion,
                                provider_model=model_name,
                                source="routes",
                                extra={
                                    "event": "queued",
                                    "provider_model": model_name,
                                    "limit_cause": adata.get('limit_cause'),
                                    "completion": completion,
                                },
                            )
                        except Exception:
                            pass
                    _perform_analysis_async(existing_bill, force_continue=force)
            
            return existing_bill
        else:
            # Bill not in database, fetch from Congress API
            logging.info(f"Bill not in database, fetching from Congress API: {search_query}")
            bill_data = congress_api.get_bill_by_number(search_query)
            if bill_data:
                bill = bill_processor.process_bill_data(bill_data)
                if bill:
                    # ETL only in processor — queue Gemini off the request path
                    _perform_analysis_async(bill)
                return bill
            return None
            
    except APIRateLimitError:
        # Re-raise the rate limit error so it can be caught by the main handler
        raise
    except Exception as e:
        logging.error(f"Error in _get_or_fetch_bill_by_number: {e}")
        return None

def _search_bills_hybrid(search_query, search_type, limit=20):
    """Hybrid search - use database when possible, fetch from API when needed"""
    bills = []
    
    try:
        # First, search our database for existing bills (prioritize display-ready)
        if search_type == 'keyword':
            # Search database bills by title/summary
            db_bills = Bill.query.filter(
                Bill.title.contains(search_query) | 
                Bill.summary.contains(search_query)
            ).order_by(Bill.display_ready.desc(), Bill.last_updated.desc()).limit(limit//2).all()  # Get half from database
        else:  # sponsor search
            # Search database bills by sponsor
            db_bills = Bill.query.filter(
                Bill.sponsor_name.contains(search_query)
            ).order_by(Bill.display_ready.desc(), Bill.last_updated.desc()).limit(limit//2).all()
        
        logging.info(f"Found {len(db_bills)} bills in database for {search_type} search: '{search_query}'")
        bills.extend(db_bills)
        
        # If we don't have enough results, supplement with API search
        if len(bills) < limit:
            remaining_limit = limit - len(bills)
            logging.info(f"Fetching {remaining_limit} additional bills from Congress API")
            
            if search_type == 'keyword':
                api_bills_data = congress_api.search_bills(search_query, limit=remaining_limit)
            else:  # sponsor
                api_bills_data = congress_api.search_bills_by_sponsor(search_query, limit=remaining_limit)
            
            if api_bills_data:
                # Get identifiers of bills we already have to avoid duplicates
                existing_identifiers = set(bill.get_bill_identifier() for bill in bills)
                
                for bill_data in api_bills_data:
                    # Check if we already have this bill
                    bill_id = f"{bill_data.get('congress', '')}-{bill_data.get('type', '').upper()}{bill_data.get('number', '')}"
                    
                    if bill_id not in existing_identifiers:
                        # Check database first before processing
                        existing_bill = _check_bill_in_database(bill_data)
                        if existing_bill:
                            bills.append(existing_bill)
                        else:
                            # Process new bill from API
                            bill = bill_processor.process_bill_data(bill_data)
                            if bill:
                                _perform_analysis_async(bill)
                                bills.append(bill)
                    
                    if len(bills) >= limit:
                        break
        
        logging.info(f"Returning {len(bills)} total bills for {search_type} search")
        return bills[:limit]  # Ensure we don't exceed limit
        
    except APIRateLimitError:
        # Re-raise the rate limit error so it can be caught by the main handler
        raise
    except Exception as e:
        logging.error(f"Error in _search_bills_hybrid: {e}")
        return bills  # Return what we have so far

def _parse_bill_identifier(search_query):
    """Parse bill identifier to extract congress, type, and number"""
    try:
        # Use the same logic as Congress API
        parts = search_query.upper().replace('-', '').replace(' ', '').replace('.', '')
        
        if parts.startswith('HR') and not parts.startswith('HRES'):
            bill_type = 'hr'
            bill_number = int(parts[2:])
        elif parts.startswith('S') and not parts.startswith('SJRES') and not parts.startswith('SRES'):
            bill_type = 's'
            bill_number = int(parts[1:])
        else:
            # Handle other bill types if needed
            return None
        
        # Default to current congress if not specified
        return 119, bill_type, bill_number
        
    except (ValueError, IndexError):
        return None

def _check_bill_in_database(bill_data):
    """Check if a bill from API data already exists in database"""
    try:
        congress = bill_data.get('congress')
        bill_type = bill_data.get('type', '').lower()
        bill_number = bill_data.get('number')
        
        if congress and bill_type and bill_number:
            return Bill.query.filter_by(
                congress=congress,
                bill_type=bill_type,
                bill_number=bill_number
            ).first()
    except Exception:
        pass
    return None

def _try_acquire_analysis_slot(bill_id):
    """Return True if this process may start analysis for bill_id."""
    if bill_id is None:
        return True
    with _analyzing_lock:
        if bill_id in _analyzing_bill_ids:
            return False
        _analyzing_bill_ids.add(bill_id)
        return True


def _analysis_is_in_flight(bill_id) -> bool:
    """True when a background analysis worker already holds this bill's slot."""
    if bill_id is None:
        return False
    with _analyzing_lock:
        return bill_id in _analyzing_bill_ids


def _release_analysis_slot(bill_id):
    if bill_id is None:
        return
    with _analyzing_lock:
        _analyzing_bill_ids.discard(bill_id)


def _try_acquire_enrichment_slot(bill_id):
    if bill_id is None:
        return True
    with _enriching_lock:
        if bill_id in _enriching_bill_ids:
            return False
        _enriching_bill_ids.add(bill_id)
        return True


def _release_enrichment_slot(bill_id):
    if bill_id is None:
        return
    with _enriching_lock:
        _enriching_bill_ids.discard(bill_id)


def _enrichment_is_deferred(bill_id) -> bool:
    if bill_id is None:
        return False
    with _enrichment_defer_lock:
        until = _enrichment_defer_until.get(bill_id)
        if until is None:
            return False
        if _time_module.time() >= until:
            _enrichment_defer_until.pop(bill_id, None)
            return False
        return True


def _mark_enrichment_deferred(bill_id, reset_seconds: float) -> None:
    if bill_id is None:
        return
    wait = max(5.0, float(reset_seconds or 60.0))
    with _enrichment_defer_lock:
        _enrichment_defer_until[bill_id] = _time_module.time() + wait


def _perform_enrichment_async(bill):
    """Queue stakeholder + policy_analysis enrichers after core analysis."""
    bill_id = getattr(bill, "id", None)
    bill_ident = None
    try:
        bill_ident = bill.get_bill_identifier()
    except Exception:
        bill_ident = None

    if _enrichment_is_deferred(bill_id):
        logging.info(
            f"Enrichment deferred (local RPM) for bill id={bill_id} ident={bill_ident}"
        )
        return

    from services.analysis_enrichers import enrichment_quota_ok

    ok, remaining, reset_in = enrichment_quota_ok(ai_analyzer)
    if not ok:
        _mark_enrichment_deferred(bill_id, reset_in or 60.0)
        logging.info(
            f"Enrichment not queued for bill id={bill_id}: "
            f"remaining_requests={remaining} (local_minute_budget)"
        )
        return

    if not _try_acquire_enrichment_slot(bill_id):
        logging.info(f"Enrichment already in flight for bill id={bill_id}")
        return

    def enrich_worker():
        from db_models import Bill
        from services.analysis_enrichers import run_downstream_enrichments

        try:
            with app.app_context():
                fresh = Bill.query.get(bill_id) if bill_id else None
                if not fresh:
                    return
                logging.info(
                    f"Starting downstream enrichments for {fresh.get_bill_identifier()}"
                )
                result = run_downstream_enrichments(fresh, ai_analyzer)
                if isinstance(result, dict) and result.get("enrichments_deferred"):
                    _mark_enrichment_deferred(
                        bill_id, result.get("enrichments_retry_after_seconds") or 60.0
                    )
                logging.info(
                    f"Downstream enrichments done for {fresh.get_bill_identifier()}"
                )
        except Exception as e:
            logging.error(f"Enrichment failed for bill id={bill_id}: {e}")
            import traceback

            logging.error(traceback.format_exc())
        finally:
            _release_enrichment_slot(bill_id)

    threading.Thread(target=enrich_worker, daemon=True).start()


def _enrichment_pending_flags(analysis_data) -> dict:
    """Flags for bill_analysis template placeholders."""
    if not analysis_data:
        return {
            "stakeholders_pending": False,
            "policy_analysis_pending": False,
            "any_enrichment_pending": False,
        }
    st = analysis_data.get("stakeholders") or {}
    pa = analysis_data.get("policy_analysis") or {}
    st_status = st.get("status") if isinstance(st, dict) else None
    pa_status = pa.get("status") if isinstance(pa, dict) else None
    st_pending = st_status in (None, "pending", "skipped")
    pa_pending = pa_status in (None, "pending", "skipped")
    # Legacy rows without status but empty template fields → treat as pending
    if isinstance(st, dict) and st_status is None:
        has_ui = bool(st.get("affected_groups") or (st.get("winners_losers") or {}).get("potential_winners"))
        st_pending = not has_ui
    if isinstance(pa, dict) and pa_status is None:
        has_deep = bool(pa.get("overall_assessment") or pa.get("category_breakdown"))
        pa_pending = not has_deep
    return {
        "stakeholders_pending": st_pending,
        "policy_analysis_pending": pa_pending,
        "any_enrichment_pending": st_pending or pa_pending,
    }


def _is_tier_b_partial(analysis_data) -> bool:
    if not analysis_data or not analysis_data.get("is_partial"):
        return False
    method = analysis_data.get("analysis_method") or ""
    tier = analysis_data.get("analysis_tier")
    return tier == "B" or method == "map_reduce_macro_chunks"


def _can_continue_tier_b_wave() -> bool:
    """Enough local RPM+TPM headroom for at least one Tier B macro map call."""
    try:
        status = ai_analyzer.get_rate_limit_status()
    except Exception:
        return False
    if status.get("is_at_limit"):
        return False
    need_tokens = int(getattr(ai_analyzer, "macro_chunk_target_tokens", 120_000)) + 1500
    if int(status.get("remaining_tokens") or 0) < need_tokens:
        return False
    if int(status.get("remaining_requests") or 0) < 2:
        return False
    return True


def _schedule_next_analysis_wave(bill_id, delay_seconds=None):
    """After local minute reset, queue another Tier B wave (UI path, no budget waits)."""
    if bill_id is None:
        return
    if delay_seconds is None:
        status = ai_analyzer.get_rate_limit_status()
        delay_seconds = max(5.0, float(status.get("time_until_reset") or 60.0) + 1.0)

    def _delayed():
        try:
            _time_module.sleep(delay_seconds)
            with app.app_context():
                bill = Bill.query.get(bill_id)
                if not bill:
                    return
                active = bill.get_active_ai_analysis()
                data = active.get_analysis_data() if active else {}
                if not _is_tier_b_partial(data):
                    return
                logging.info(
                    f"Scheduling delayed Tier B wave for {bill.get_bill_identifier()} "
                    f"after {delay_seconds:.1f}s"
                )
                _perform_analysis_async(bill, force_continue=True)
        except Exception as e:
            logging.error(f"Delayed analysis wave failed for bill id={bill_id}: {e}")

    threading.Thread(target=_delayed, daemon=True).start()


def _perform_analysis_if_needed(bill, force_continue=False, allow_budget_waits=False):
    """Perform comprehensive AI analysis on bill if not already done - equivalent to workflow orchestrator.

    When force_continue=True (async resume of a partial), re-run analyze_bill even if an
    active analysis already exists.
    allow_budget_waits: False for UI waves (fast); True for offline/backfill callers.
    """
    import time
    try:
        # Check both old and new database structure for existing analysis
        has_old_analysis = bool(bill.ai_analysis)
        has_new_analysis = bool(bill.get_active_ai_analysis())

        if force_continue or (not has_old_analysis and not has_new_analysis):
            logging.info(
                f"{'Continuing' if force_continue else 'Performing'} comprehensive AI analysis "
                f"for {bill.get_bill_identifier()}"
            )
            
            # Get full text for analysis
            full_text = bill.get_full_text()
            if not full_text:
                logging.warning(f"No full text available for analysis: {bill.get_bill_identifier()}")
                return
                
            text_length = len(full_text)
            start_time = time.time()
            
            logging.info(f"Starting enhanced AI analysis for {bill.get_bill_identifier()} "
                        f"(text length: {text_length:,} characters)")
            
            analysis = ai_analyzer.analyze_bill(
                bill, bill.title, allow_budget_waits=allow_budget_waits
            )
            
            processing_time = time.time() - start_time
            
            if analysis:
                # The EnhancedAIAnalyzer automatically handles new database structure creation
                logging.info(f"✅ Enhanced AI analysis completed for: {bill.get_bill_identifier()}")
                
                # Policy categories and summaries are now automatically stored by EnhancedAIAnalyzer
                # using the new database structure with proper versioning and display_ready status
                
                # Log comprehensive analysis information (same as workflow orchestrator)
                chunks_analyzed = analysis.get('chunks_analyzed', 0)
                analysis_method = analysis.get('analysis_method', 'enhanced_search')
                
                logging.info(f"  📊 Method: {analysis_method}")
                logging.info(f"  🔧 Chunks analyzed: {chunks_analyzed}")
                logging.info(f"  📝 Text processed: {text_length:,} characters")
                logging.info(f"  ⏱️ Processing time: {processing_time:.2f} seconds")
                if processing_time > 0:
                    logging.info(f"  🚀 Processing speed: {text_length/processing_time:,.0f} chars/sec")
                
                # Log analysis components
                if 'summary' in analysis:
                    logging.info(f"  📝 Summary generated")
                if 'policy_implications' in analysis:
                    policy_data = analysis['policy_implications']
                    primary_area = policy_data.get('primary_category') or policy_data.get('primary_policy_area', 'Unknown')
                    logging.info(f"  🎯 Primary policy area: {primary_area}")
                if 'stakeholders' in analysis:
                    logging.info(f"  👥 Stakeholder analysis completed")
                if 'hidden_provisions' in analysis:
                    hidden_data = analysis['hidden_provisions']
                    if isinstance(hidden_data, dict):
                        provisions_count = len(hidden_data.get('detected_provisions', []))
                        risk_score = hidden_data.get('overall_hidden_risk_score', 0)
                        logging.info(f"  🕵️ Hidden provisions: {provisions_count} detected, risk: {risk_score:.2f}")
                if 'complexity_assessment' in analysis:
                    complexity_data = analysis['complexity_assessment']
                    if isinstance(complexity_data, dict):
                        complexity_score = complexity_data.get('complexity_score', 0)
                        logging.info(f"  🧮 Complexity score: {complexity_score:.2f}")
                if 'controversy_score' in analysis:
                    controversy_score = analysis.get('controversy_score', 0)
                    logging.info(f"  ⚡ Controversy score: {controversy_score:.2f}")
                if 'overall_risk_score' in analysis:
                    risk_score = analysis.get('overall_risk_score', 0)
                    logging.info(f"  🚨 Overall risk score: {risk_score:.2f}")
                
                # Legacy compatibility - EnhancedAIAnalyzer already handles new structure
                # Old field set automatically by analyzer for backward compatibility
                
                logging.info(f"Complete analysis pipeline finished for {bill.get_bill_identifier()}")
            else:
                logging.warning(f"No analysis results returned for {bill.get_bill_identifier()}")
                
    except AIAnalysisPartialError as e:
        # Log partial analysis completion but re-raise for user notification
        logging.info(f"⚠️ Partial AI analysis completed for {bill.get_bill_identifier()}: {e.completion_percentage:.1f}% complete")
        logging.info(f"  📊 Chunks analyzed: {e.completed_chunks}/{e.total_chunks}")
        logging.info(f"  💾 Partial results saved to database")
        
        # Re-raise partial analysis errors so they can be caught by the main handler
        raise
    except Exception as e:
        logging.error(f"Error performing comprehensive analysis for {bill.get_bill_identifier()}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        if force_continue:
            raise


def _perform_analysis_async(bill, force_continue=False):
    """Perform AI analysis in a background thread to avoid blocking the web request.

    Reloads Bill by id inside the worker to avoid detached-instance failures.
    When force_continue=True, re-runs analyze_bill for partial resume paths.
    Emits continuation_finished OpsAlert when the job ends.
    UI waves use allow_budget_waits=False; schedules another wave if still Tier B partial.
    """
    bill_id = getattr(bill, 'id', None)
    bill_ident = None
    try:
        bill_ident = bill.get_bill_identifier()
    except Exception:
        bill_ident = None
    model_name = getattr(ai_analyzer, 'model_name', GEMINI_MODEL)

    if not _try_acquire_analysis_slot(bill_id):
        # Refresh / auto-poll while a wave is running — log only, do not spam OpsAlert rows
        logging.info(
            f"Skipping analysis spawn for bill id={bill_id} — already in flight"
        )
        return

    def analysis_worker():
        """Worker function that runs the analysis in background"""
        from db_models import Bill
        from services.ops_alert_service import (
            CONTINUATION_FINISHED,
            UNKNOWN,
            notify_gemini_failure,
        )

        try:
            with app.app_context():
                fresh_bill = Bill.query.get(bill_id) if bill_id else None
                if not fresh_bill:
                    logging.error(f"❌ Background analysis: bill id={bill_id} not found")
                    notify_gemini_failure(
                        CONTINUATION_FINISHED,
                        f"Background analysis failed: bill id={bill_id} not found",
                        severity="error",
                        bill_identifier=bill_ident,
                        bill_id=bill_id,
                        provider_model=model_name,
                        source="routes",
                        extra={"event": "finished", "error": "bill_not_found"},
                    )
                    return

                ident = fresh_bill.get_bill_identifier()
                logging.info(f"🔄 Starting background analysis for {ident} (force_continue={force_continue})")
                try:
                    _perform_analysis_if_needed(
                        fresh_bill,
                        force_continue=force_continue,
                        allow_budget_waits=False,
                    )
                except AIAnalysisPartialError as e:
                    logging.info(
                        f"⚠️ Background analysis partial for {ident}: "
                        f"{e.completion_percentage:.1f}% complete"
                    )
                    notify_gemini_failure(
                        CONTINUATION_FINISHED,
                        (
                            f"Continuation finished still partial at {e.completion_percentage:.1f}% "
                            f"(model={model_name}, chunks={e.completed_chunks}/{e.total_chunks})."
                        ),
                        severity="warning",
                        bill=fresh_bill,
                        completion_percentage=e.completion_percentage,
                        provider_model=model_name,
                        source="routes",
                        extra={
                            "event": "finished",
                            "is_partial": True,
                            "provider_model": model_name,
                            "completed_chunks": e.completed_chunks,
                            "total_chunks": e.total_chunks,
                            "chunks": f"{e.completed_chunks}/{e.total_chunks}",
                        },
                    )
                    # Auto-schedule next Tier B wave after minute reset
                    _schedule_next_analysis_wave(bill_id)
                    return

                # Inspect stored analysis for finished status
                active = fresh_bill.get_active_ai_analysis()
                data = active.get_analysis_data() if active else {}
                is_partial = bool(data.get('is_partial'))
                completion = data.get('completion_percentage')
                if completion is None and active:
                    completion = 100.0 if not is_partial else None
                severity = "warning" if is_partial else "info"
                notify_gemini_failure(
                    CONTINUATION_FINISHED,
                    (
                        f"Continuation finished for {ident} "
                        f"(model={model_name}, "
                        f"completion={completion if completion is not None else 'n/a'}%, "
                        f"is_partial={is_partial})."
                    ),
                    severity=severity,
                    bill=fresh_bill,
                    completion_percentage=completion,
                    provider_model=getattr(active, 'provider_model', None) or model_name,
                    source="routes",
                    extra={
                        "event": "finished",
                        "is_partial": is_partial,
                        "provider_model": getattr(active, 'provider_model', None) or model_name,
                        "analysis_tier": data.get("analysis_tier"),
                        "chars_analyzed": data.get("chars_analyzed"),
                        "total_chars": data.get("total_chars"),
                    },
                )
                if _is_tier_b_partial(data):
                    _schedule_next_analysis_wave(bill_id)
                elif not is_partial:
                    from services.analysis_enrichers import enrichments_need_work

                    if enrichments_need_work(data):
                        _perform_enrichment_async(fresh_bill)
                logging.info(f"✅ Background analysis completed for {ident}")
        except Exception as e:
            logging.error(f"❌ Background analysis failed for bill id={bill_id}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            try:
                notify_gemini_failure(
                    CONTINUATION_FINISHED,
                    f"Continuation failed: {type(e).__name__}",
                    severity="error",
                    bill_identifier=bill_ident,
                    bill_id=bill_id,
                    provider_model=model_name,
                    source="routes",
                    extra={
                        "event": "finished",
                        "error": type(e).__name__,
                        "failure_class_hint": UNKNOWN,
                    },
                )
            except Exception:
                pass
        finally:
            _release_analysis_slot(bill_id)

    thread = threading.Thread(target=analysis_worker, daemon=True)
    thread.start()

    logging.info(f"🚀 Background analysis started for bill id={bill_id}")


def _store_policy_categories_with_sneakiness(bill, categories, analysis=None):
    """Store policy category mappings for the bill, including sneakiness score per category"""
    try:
        from db_models import BillCategoryMapping, PolicyCategory
        import re
        import json
        categories_stored = 0

        # Prepare sneakiness mapping if analysis is provided
        sneakiness_by_category = {}
        if analysis and 'hidden_provisions' in analysis:
            hidden_provisions = analysis['hidden_provisions'].get('detected_provisions', [])
            # Build a mapping: category_name -> max sneakiness score
            for provision in hidden_provisions:
                provision_text = (provision.get('text') or '') + ' ' + (provision.get('type') or '')
                risk_level = provision.get('risk_level', 'low')
                confidence = provision.get('confidence_score', 0.5)
                risk_value = {'low': 0.2, 'medium': 0.5, 'high': 0.8}.get(risk_level, 0.2)
                sneakiness_score = risk_value * confidence
                for cat in categories:
                    area = cat.get('area', '')
                    if area and re.search(re.escape(area), provision_text, re.IGNORECASE):
                        prev = sneakiness_by_category.get(area, 0.0)
                        sneakiness_by_category[area] = max(prev, sneakiness_score)
        
        for category_data in categories:
            area = category_data.get('area')
            if not area:
                continue
            try:
                # Find or create policy category
                policy_category = PolicyCategory.query.filter_by(name=area).first()
                if not policy_category:
                    policy_category = PolicyCategory(
                        name=area,
                        display_name=area.title(),
                        description=f"Policy area: {area}",
                        color='#007bff',
                        icon='policy',
                        is_active=True
                    )
                    db.session.add(policy_category)
                    db.session.flush()
                    logging.info(f"Created new policy category: {area}")
                
                mapping = BillCategoryMapping.query.filter_by(
                    bill_id=bill.id,
                    policy_category_id=policy_category.id
                ).first()
                
                # Extract relevance score from category data or use default
                relevance_score = category_data.get('impact_level', 'medium')
                if relevance_score == 'high':
                    score = 0.9
                elif relevance_score == 'medium':
                    score = 0.7
                elif relevance_score == 'low':
                    score = 0.5
                else:
                    score = 0.8
                
                sneakiness_score = sneakiness_by_category.get(area, 0.0)
                
                # Extract section reference and title information
                section_reference = None
                if 'section' in category_data:
                    section_ref = category_data['section']
                elif 'reasoning' in category_data:
                    # Try to extract section info from reasoning text
                    reasoning = category_data['reasoning']
                    import re
                    section_match = re.search(r'[Ss]ection\s+(\d+[\w\-\.]*)', reasoning)
                    if section_match:
                        section_reference = f"Section {section_match.group(1)}"
                
                # Include title in section reference if available
                if category_data.get('title') and section_reference:
                    section_reference = f"{section_reference}: {category_data['title'][:100]}"
                elif category_data.get('title'):
                    section_reference = category_data['title'][:150]
                
                if not mapping:
                    mapping = BillCategoryMapping(
                        bill_id=bill.id,
                        policy_category_id=policy_category.id,
                        relevance_score=score,
                        category_specific_analysis=json.dumps(category_data),
                        sneakiness_score=sneakiness_score,
                        section_reference=section_reference
                    )
                    db.session.add(mapping)
                    categories_stored += 1
                    logging.info(f"Created category mapping: {bill.get_bill_identifier()} -> {area} (score: {score}, sneakiness: {sneakiness_score})")
                else:
                    mapping.category_specific_analysis = json.dumps(category_data)
                    mapping.sneakiness_score = sneakiness_score
                    mapping.section_reference = section_reference
                    logging.info(f"Updated existing category mapping: {bill.get_bill_identifier()} -> {area} (sneakiness: {sneakiness_score})")
                    
            except Exception as category_error:
                logging.error(f"Error processing category '{area}': {category_error}")
                continue
        
        if categories_stored > 0:
            db.session.commit()
            logging.info(f"Successfully stored {categories_stored} policy category mappings for {bill.get_bill_identifier()}")
        else:
            logging.warning(f"No new policy category mappings were stored for {bill.get_bill_identifier()}")
            
    except Exception as e:
        logging.error(f"Error storing policy categories for {bill.get_bill_identifier()}: {e}")
        db.session.rollback()

def _get_unique_recent_bills(limit=10):
    """Get recent bills, using first record found for each unique bill (same logic as bill detail page)"""
    try:
        # Get all display-ready bills ordered by last_updated desc
        all_bills = Bill.query.filter_by(display_ready=True).order_by(Bill.last_updated.desc()).limit(limit*3).all()
        
        # Use a dictionary to keep track of unique bills (first version found)
        unique_bills = {}
        bill_keys_seen = set()
        
        for bill in all_bills:
            # Create unique key based on congress, type, and number
            bill_key = f"{bill.congress}-{bill.bill_type}-{bill.bill_number}"
            
            # Only keep the first version of each unique bill (same as .first() logic)
            if bill_key not in bill_keys_seen:
                # Use the same logic as bill detail page: get first display-ready record for this bill
                first_bill = Bill.query.filter_by(
                    congress=bill.congress,
                    bill_type=bill.bill_type,
                    bill_number=bill.bill_number,
                    display_ready=True
                ).first()
                unique_bills[bill_key] = first_bill
                bill_keys_seen.add(bill_key)
            
            # Stop once we have enough unique bills
            if len(unique_bills) >= limit:
                break
        
        # Return the unique bills sorted by last_updated desc
        result_bills = list(unique_bills.values())
        result_bills.sort(key=lambda b: b.last_updated, reverse=True)
        
        logging.info(f"Returning {len(result_bills)} unique recent bills (first record for each bill)")
        return result_bills[:limit]
        
    except Exception as e:
        logging.error(f"Error getting unique recent bills: {e}")
        # Fallback to active and display-ready bills only
        return Bill.query.filter_by(active=True, display_ready=True).order_by(Bill.last_updated.desc()).limit(limit).all()

def fetch_bill_actions_from_api(bill):
    """Fetch and store bill actions from Congress API"""
    try:
        if not bill.actions:  # Only fetch if no actions exist
            actions_data = congress_api.get_bill_actions(bill.congress, bill.bill_type, bill.bill_number)
            if actions_data and 'actions' in actions_data:
                for action_info in actions_data['actions']:
                    # Parse action data
                    action_date = None
                    if action_info.get('actionDate'):
                        try:
                            action_date = datetime.strptime(action_info['actionDate'], '%Y-%m-%d')
                        except:
                            pass
                    
                    action = BillAction(
                        bill_id=bill.id,
                        action_date=action_date or datetime.utcnow(),
                        action_type=action_info.get('type', 'Unknown'),
                        action_text=action_info.get('text', ''),
                        action_description=action_info.get('description', ''),
                        source_system=action_info.get('sourceSystem', {}).get('code', ''),
                        source_system_name=action_info.get('sourceSystem', {}).get('name', '')
                    )
                    db.session.add(action)
                
                db.session.commit()
                logging.info(f"Fetched {len(actions_data['actions'])} actions for bill {bill.get_bill_identifier()}")
    except Exception as e:
        logging.error(f"Error fetching bill actions: {str(e)}")

@app.route('/bill/<int:congress>/<bill_type>/<int:bill_number>')
def bill_analysis(congress, bill_type, bill_number):
    """Display detailed analysis of a specific bill"""
    # Prefer active + display-ready versions (avoid stale inactive rows from re-ingest)
    bill = Bill.query.filter_by(
        congress=congress,
        bill_type=bill_type.lower(),
        bill_number=bill_number,
    ).order_by(
        Bill.active.desc(),
        Bill.display_ready.desc(),
        Bill.id.desc(),
    ).first()
    
    if not bill:
        # Fetch from Congress API if not in database
        try:
            bill_data = congress_api.get_bill_details(congress, bill_type, bill_number)
            if bill_data:
                bill = bill_processor.process_bill_data(bill_data)
                if bill:
                    _perform_analysis_async(bill)
            else:
                flash('Bill not found', 'error')
                return redirect(url_for('bill_search'))
        except APIRateLimitError as e:
            logging.warning(f"Congress API rate limit exceeded while fetching bill: {str(e)}")
            flash('Unable to fetch new bill details due to API rate limits. Please try again later.', 'warning')
            return redirect(url_for('bill_search'))
        except Exception as e:
            logging.error(f"Error fetching bill: {str(e)}")
            flash('Error loading bill details', 'error')
            return redirect(url_for('bill_search'))
    
    # Fetch bill actions if not already present
    fetch_bill_actions_from_api(bill)
    
    # Perform AI analysis if not already done (use new database structure)
    partial_analysis_warning = None
    continuation_queued = False
    try:
        active_analysis = bill.get_active_ai_analysis()
        if active_analysis:
            analysis = active_analysis.get_analysis_data()
            # Resume incomplete Tier B partials (async). Clear non-Tier-B partials and re-ingest instead.
            if analysis and analysis.get('is_partial', False):
                completion = analysis.get('completion_percentage', 0)
                completed_chunks = analysis.get('chunks_analyzed', 0)
                total_chunks = analysis.get(
                    'total_chunks_available',
                    completed_chunks + analysis.get('remaining_chunks', 0),
                )
                remaining_chunks = analysis.get(
                    'remaining_chunks',
                    max(0, total_chunks - completed_chunks) if total_chunks else 0,
                )
                limit_cause = analysis.get('limit_cause') or 'local_minute_budget'
                model_name = getattr(ai_analyzer, 'model_name', GEMINI_MODEL)
                chars_analyzed = analysis.get('chars_analyzed', 0)
                total_chars = analysis.get('total_chars', 0)
                is_tier_b = _is_tier_b_partial(analysis)

                coverage_note = (
                    f"{chars_analyzed:,}/{total_chars:,} characters"
                    if total_chars
                    else f"{completed_chunks}/{total_chunks} sections"
                )
                partial_analysis_warning = {
                    'message': (
                        f"Analysis is only {completion:.1f}% complete "
                        f"({coverage_note}; model={model_name}, limit_cause={limit_cause})."
                    ),
                    'completion_percentage': completion,
                    'completed_chunks': completed_chunks,
                    'total_chunks': total_chunks,
                    'remaining_chunks': remaining_chunks,
                    'chars_analyzed': chars_analyzed,
                    'total_chars': total_chars,
                    'limit_cause': limit_cause,
                    'provider_model': model_name,
                    'analysis_tier': analysis.get('analysis_tier'),
                    'continuation_queued': False,
                }

                if is_tier_b and completion < 100:
                    can_analyze = _can_continue_tier_b_wave()
                    if _analysis_is_in_flight(getattr(bill, "id", None)):
                        # Already running — keep UI "queued" state without new OpsAlert spam
                        logging.info(
                            f"Partial AI analysis on bill detail ({completion:.1f}% complete), "
                            f"continuation already in flight for {bill.get_bill_identifier()}"
                        )
                        continuation_queued = True
                        partial_analysis_warning['continuation_queued'] = True
                        partial_analysis_warning['message'] += (
                            " Background analysis is already running; "
                            "this page will update when you refresh — each wave adds more coverage."
                        )
                    elif can_analyze:
                        logging.info(
                            f"Partial AI analysis on bill detail ({completion:.1f}% complete), "
                            f"queueing continued analysis for {bill.get_bill_identifier()}"
                        )
                        try:
                            from services.ops_alert_service import (
                                CONTINUATION_QUEUED,
                                notify_gemini_failure,
                            )
                            notify_gemini_failure(
                                CONTINUATION_QUEUED,
                                (
                                    f"Continuation queued at {completion:.1f}% "
                                    f"(model={model_name}, chunks={completed_chunks}/{total_chunks}, "
                                    f"limit_cause={limit_cause})."
                                ),
                                severity="info",
                                bill=bill,
                                completion_percentage=completion,
                                provider_model=model_name,
                                source="routes",
                                extra={
                                    "event": "queued",
                                    "provider_model": model_name,
                                    "model": model_name,
                                    "completed_chunks": completed_chunks,
                                    "total_chunks": total_chunks,
                                    "limit_cause": limit_cause,
                                    "chunks": f"{completed_chunks}/{total_chunks}",
                                    "completion": completion,
                                    "chars_analyzed": chars_analyzed,
                                    "total_chars": total_chars,
                                },
                            )
                        except Exception:
                            pass
                        _perform_analysis_async(bill, force_continue=True)
                        continuation_queued = True
                        partial_analysis_warning['continuation_queued'] = True
                        partial_analysis_warning['message'] += (
                            " Background analysis is running under free-tier rate limits; "
                            "this page will update when you refresh — each wave adds more coverage."
                        )
                    else:
                        logging.info(
                            f"Partial AI analysis on bill detail ({completion:.1f}% complete), "
                            f"insufficient API quota for {bill.get_bill_identifier()}"
                        )
                        try:
                            from services.ops_alert_service import (
                                PARTIAL_ANALYSIS,
                                notify_gemini_failure,
                            )
                            notify_gemini_failure(
                                PARTIAL_ANALYSIS,
                                (
                                    f"Partial analysis stuck at {completion:.1f}% on bill detail; "
                                    f"insufficient local quota to resume "
                                    f"(model={model_name}, chunks={completed_chunks}/{total_chunks}, "
                                    f"limit_cause={limit_cause})."
                                ),
                                severity="warning",
                                bill=bill,
                                completion_percentage=completion,
                                provider_model=model_name,
                                source="routes",
                                extra={
                                    "provider_model": model_name,
                                    "model": model_name,
                                    "completed_chunks": completed_chunks,
                                    "total_chunks": total_chunks,
                                    "limit_cause": limit_cause,
                                    "chunks": f"{completed_chunks}/{total_chunks}",
                                    "resume_blocked": True,
                                },
                            )
                        except Exception:
                            pass
                        # Still schedule a delayed wave after minute reset
                        _schedule_next_analysis_wave(getattr(bill, "id", None))
                        continuation_queued = True
                        partial_analysis_warning['continuation_queued'] = True
                        partial_analysis_warning['message'] += (
                            " Next analysis wave is scheduled after the free-tier minute resets; "
                            "this page will update when you refresh."
                        )
        elif bill.get_ai_analysis():
            analysis = bill.get_ai_analysis()  # Fallback to old structure
        else:
            # No analysis exists — queue async (never block page on Gemini / minute waits)
            logging.info(
                f"Queueing AI analysis for bill analysis page: {bill.get_bill_identifier()}"
            )
            model_name = getattr(ai_analyzer, 'model_name', GEMINI_MODEL)
            _perform_analysis_async(bill)
            continuation_queued = True
            analysis = {
                "status": "queued",
                "message": (
                    "Background analysis is running (free-tier rate limits). "
                    "This page will update when you refresh."
                ),
            }
            partial_analysis_warning = {
                'message': (
                    f"AI analysis was queued (model={model_name}). "
                    "Background analysis is running under free-tier rate limits; "
                    "refresh to see progress — each wave adds more coverage."
                ),
                'completion_percentage': 0,
                'completed_chunks': 0,
                'total_chunks': 0,
                'remaining_chunks': 0,
                'provider_model': model_name,
                'continuation_queued': True,
            }
    except AIAnalysisPartialError as e:
        logging.warning(f"AI analysis was partial for bill {bill.get_bill_identifier()}: {str(e)}")
        model_name = getattr(ai_analyzer, 'model_name', GEMINI_MODEL)
        try:
            from services.ops_alert_service import (
                PARTIAL_ANALYSIS,
                notify_gemini_failure,
            )
            notify_gemini_failure(
                PARTIAL_ANALYSIS,
                str(e),
                severity="warning",
                bill=bill,
                completion_percentage=e.completion_percentage,
                provider_model=model_name,
                source="routes",
                extra={
                    "provider_model": model_name,
                    "model": model_name,
                    "completed_chunks": e.completed_chunks,
                    "total_chunks": e.total_chunks,
                    "chunks": f"{e.completed_chunks}/{e.total_chunks}",
                },
            )
        except Exception:
            pass
        # Still try to get the partial analysis that was stored
        new_analysis = bill.get_active_ai_analysis()
        if new_analysis:
            analysis = new_analysis.get_analysis_data()
        elif bill.get_ai_analysis():
            analysis = bill.get_ai_analysis()  # Fallback
        else:
            analysis = {"error": "Unable to perform AI analysis at this time"}
        
        # Set warning message for the template
        partial_analysis_warning = {
            'message': f"Analysis is only {e.completion_percentage:.1f}% complete due to AI API rate limits.",
            'completion_percentage': e.completion_percentage,
            'completed_chunks': e.completed_chunks,
            'total_chunks': e.total_chunks,
            'remaining_chunks': e.total_chunks - e.completed_chunks,
            'provider_model': model_name,
            'continuation_queued': continuation_queued,
        }
    
    # Calculate user alignment score if user is logged in (only when base analysis exists)
    alignment_score = None
    user_analysis = None
    if current_user.is_authenticated:
        user_prefs = current_user.get_policy_preferences()
        has_usable_analysis = (
            analysis
            and isinstance(analysis, dict)
            and not analysis.get('error')
            and analysis.get('status') != 'queued'
        )
        if user_prefs and has_usable_analysis:
            try:
                alignment_score = ai_analyzer.calculate_alignment_score(
                    analysis, user_prefs
                )
                user_analysis = ai_analyzer.generate_user_specific_analysis(
                    analysis, user_prefs, alignment_score
                )
            except Exception as e:
                logging.error(f"Error calculating alignment: {str(e)}")
    
    # Get bill actions (refresh from database after potential fetch)
    bill_actions = bill.actions

    # Queue downstream enrichments when core is done but stakeholders/policy_analysis pending
    enrichment_flags = _enrichment_pending_flags(
        analysis if isinstance(analysis, dict) else None
    )
    if (
        isinstance(analysis, dict)
        and analysis.get("status") != "queued"
        and not analysis.get("error")
        and not analysis.get("is_partial")
        and enrichment_flags["any_enrichment_pending"]
        and not _enrichment_is_deferred(getattr(bill, "id", None))
    ):
        from services.analysis_enrichers import enrichment_quota_ok

        ok, _remaining, reset_in = enrichment_quota_ok(ai_analyzer)
        if ok:
            _perform_enrichment_async(bill)
            enrichment_flags["enrichment_queued"] = True
        else:
            _mark_enrichment_deferred(getattr(bill, "id", None), reset_in or 60.0)
            enrichment_flags["enrichment_queued"] = False
    else:
        enrichment_flags["enrichment_queued"] = False

    return render_template('bill_analysis.html', 
                         bill=bill, 
                         analysis=analysis,
                         alignment_score=alignment_score,
                         user_analysis=user_analysis,
                         bill_actions=bill_actions,
                         partial_analysis_warning=partial_analysis_warning,
                         enrichment_flags=enrichment_flags)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """User profile and policy preferences management"""
    if 'user_id' not in session:
        # Create a temporary user session for demo purposes
        session['user_id'] = 1
        user = User.query.get(1)
        if not user:
            user = User(username='demo_user', email='demo@example.com')
            db.session.add(user)
            db.session.commit()
            session['user_id'] = user.id
    
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            # Update policy preferences
            preferences = {}
            policy_areas = [
                'healthcare', 'environment', 'economy', 'education', 'defense',
                'immigration', 'civil_rights', 'technology', 'agriculture',
                'energy', 'transportation', 'housing', 'tax_policy',
                'foreign_policy', 'criminal_justice', 'social_services'
            ]
            
            for area in policy_areas:
                importance = request.form.get(f'{area}_importance', 'medium')
                stance = request.form.get(f'{area}_stance', 'neutral')
                preferences[area] = {
                    'importance': importance,
                    'stance': stance
                }
            
            user.set_policy_preferences(preferences)
            
            # Update alert preferences
            user.alert_frequency = request.form.get('alert_frequency', 'weekly')
            user.alert_enabled = 'alert_enabled' in request.form
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            
        except Exception as e:
            logging.error(f"Error updating profile: {str(e)}")
            flash('Error updating profile. Please try again.', 'error')
        
        return redirect(url_for('profile'))
    
    current_preferences = user.get_policy_preferences()
    return render_template('profile.html', user=user, preferences=current_preferences)

@app.route('/alerts')
@login_required
def alerts():
    """Display user alerts and notifications"""
    # Get all alerts for the user
    alerts = Alert.query.filter_by(user_id=current_user.id)\
                       .order_by(Alert.created_at.desc()).all()
    
    return render_template('alerts.html', alerts=alerts)

@app.route('/mark_alert_read/<int:alert_id>')
@login_required
def mark_alert_read(alert_id):
    """Mark an alert as read"""
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if alert:
        alert.is_read = True
        db.session.commit()
        flash('Alert marked as read', 'success')
    else:
        flash('Alert not found', 'error')
    
    return redirect(url_for('alerts'))

@app.route('/add_to_watchlist/<int:bill_id>')
@login_required
def add_to_watchlist(bill_id):
    """Add a bill to user's watchlist"""
    bill = Bill.query.get(bill_id)
    if not bill:
        flash('Bill not found', 'error')
        return redirect(url_for('bill_search'))
    
    # Check if already in watchlist
    existing = WatchlistItem.query.filter_by(
        user_id=current_user.id, 
        bill_id=bill_id
    ).first()
    
    if existing:
        flash('Bill is already in your watchlist', 'info')
    else:
        watchlist_item = WatchlistItem(
            user_id=current_user.id,
            bill_id=bill_id
        )
        db.session.add(watchlist_item)
        db.session.commit()
        flash('Bill added to watchlist', 'success')
    
    return redirect(url_for('bill_analysis', 
                          congress=bill.congress, 
                          bill_type=bill.bill_type, 
                          bill_number=bill.bill_number))

@app.route('/api/generate_alerts')
@login_required
def generate_alerts():
    """Generate alerts for the current user based on their policy preferences"""
    try:
        # This would typically be called by a background job
        # For now, just return a success message
        return jsonify({'status': 'success', 'message': 'Alerts generation initiated'})
    except Exception as e:
        logging.error(f"Error generating alerts: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to generate alerts'}), 500

@app.route('/api/bill/<int:congress>/<bill_type>/<int:bill_number>/text')
def get_bill_text(congress, bill_type, bill_number):
    """API endpoint to get bill text"""
    try:
        bill = Bill.query.filter_by(
            congress=congress, 
            bill_type=bill_type.lower(), 
            bill_number=bill_number
        ).first()
        
        if not bill:
            return jsonify({'error': 'Bill not found'}), 404
        
        full_text = bill.get_full_text()
        if not full_text:
            return jsonify({'error': 'Bill text not available'}), 404
        
        return jsonify({
            'congress': congress,
            'bill_type': bill_type,
            'bill_number': bill_number,
            'title': bill.title,
            'text': full_text
        })
        
    except Exception as e:
        logging.error(f"Error getting bill text: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/workflow/start', methods=['POST'])
def start_workflow():
    """Start the bill processing workflow"""
    try:
        orchestrator = get_workflow_orchestrator()
        result = orchestrator.start_workflow_web()
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error starting workflow: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/stop', methods=['POST'])
def stop_workflow():
    """Stop the bill processing workflow"""
    try:
        orchestrator = get_workflow_orchestrator()
        result = orchestrator.stop_workflow_web()
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error stopping workflow: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/status')
def get_workflow_status():
    """Get the current workflow status"""
    try:
        orchestrator = get_workflow_orchestrator()
        status = orchestrator.get_workflow_status()
        return jsonify(status)
    except Exception as e:
        logging.error(f"Error getting workflow status: {str(e)}")
        return jsonify({
            'is_running': False,
            'queue_size': 0,
            'statistics': {
                'bills_discovered': 0,
                'bills_processed': 0,
                'bills_analyzed': 0,
                'alerts_generated': 0,
                'errors': 0
            },
            'last_run': None,
            'error_message': str(e)
        })

@app.route('/api/workflow/recent')
def get_recent_workflow_items():
    """Get recent workflow items"""
    try:
        orchestrator = get_workflow_orchestrator()
        limit = request.args.get('limit', 10, type=int)
        items = orchestrator.get_recent_workflow_items(limit)
        return jsonify({'items': items})
    except Exception as e:
        logging.error(f"Error getting recent workflow items: {str(e)}")
        # Return empty items list if there's an error
        return jsonify({'items': [], 'error_message': str(e)})

@app.route('/workflow')
def workflow_dashboard():
    """Workflow dashboard for monitoring bill processing"""
    return render_template('workflow_dashboard.html')


def _ops_alerts_query(unread_only=None, bill=None, failure_class=None):
    """Build filtered OpsAlert query."""
    q = OpsAlert.query
    if unread_only:
        q = q.filter_by(is_read=False)
    if bill:
        bill_q = bill.strip()
        if bill_q:
            q = q.filter(OpsAlert.bill_identifier.ilike(f"%{bill_q}%"))
    if failure_class:
        q = q.filter_by(failure_class=failure_class)
    return q.order_by(OpsAlert.created_at.desc())


@app.route('/ops/logs')
def ops_logs():
    """Programmer-facing ops logs (Gemini failures, etc.) with filters."""
    view = request.args.get('view', 'unread')  # unread | all
    bill = request.args.get('bill', '').strip()
    failure_class = request.args.get('failure_class', '').strip() or None
    unread_only = view != 'all'

    alerts = _ops_alerts_query(
        unread_only=unread_only,
        bill=bill or None,
        failure_class=failure_class,
    ).limit(200).all()

    unread_count = OpsAlert.query.filter_by(is_read=False).count()
    failure_classes = [
        row[0]
        for row in db.session.query(OpsAlert.failure_class).distinct().order_by(OpsAlert.failure_class).all()
    ]

    return render_template(
        'ops_logs.html',
        alerts=alerts,
        view=view,
        bill=bill,
        failure_class=failure_class or '',
        failure_classes=failure_classes,
        unread_count=unread_count,
    )


@app.route('/ops/logs/<int:alert_id>/read', methods=['POST'])
def ops_log_mark_read(alert_id):
    alert = OpsAlert.query.get_or_404(alert_id)
    alert.is_read = True
    db.session.commit()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'id': alert_id, 'is_read': True})
    next_url = request.form.get('next') or request.referrer or url_for('ops_logs')
    return redirect(next_url)


@app.route('/ops/logs/<int:alert_id>/unread', methods=['POST'])
def ops_log_mark_unread(alert_id):
    alert = OpsAlert.query.get_or_404(alert_id)
    alert.is_read = False
    db.session.commit()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True, 'id': alert_id, 'is_read': False})
    next_url = request.form.get('next') or request.referrer or url_for('ops_logs', view='all')
    return redirect(next_url)


@app.route('/ops/logs/read-all', methods=['POST'])
def ops_logs_mark_all_read():
    view = request.form.get('view', 'unread')
    bill = request.form.get('bill', '').strip()
    failure_class = request.form.get('failure_class', '').strip() or None
    unread_only = view != 'all'
    q = _ops_alerts_query(
        unread_only=True if unread_only else False,
        bill=bill or None,
        failure_class=failure_class,
    )
    # Only mark currently unread rows
    updated = q.filter_by(is_read=False).update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    flash(f'Marked {updated} alert(s) as read.', 'success')
    return redirect(url_for('ops_logs', view=view, bill=bill or None, failure_class=failure_class))


@app.route('/ops/logs/unread-all', methods=['POST'])
def ops_logs_mark_all_unread():
    """Mark filtered alerts as unread again (typically used from All view)."""
    view = request.form.get('view', 'all')
    bill = request.form.get('bill', '').strip()
    failure_class = request.form.get('failure_class', '').strip() or None
    q = _ops_alerts_query(
        unread_only=False,
        bill=bill or None,
        failure_class=failure_class,
    )
    updated = q.filter_by(is_read=True).update({'is_read': False}, synchronize_session=False)
    db.session.commit()
    flash(f'Marked {updated} alert(s) as unread.', 'success')
    return redirect(url_for('ops_logs', view=view, bill=bill or None, failure_class=failure_class))


@app.context_processor
def inject_ops_unread_count():
    try:
        count = OpsAlert.query.filter_by(is_read=False).count()
    except Exception:
        count = 0
    return {'ops_nav_unread_count': count}


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500
