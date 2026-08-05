"""
Persist hidden provisions / sneaky riders into the HiddenProvision table.

Canonical read source for UI, search badges, and notifications.
Analyzer still emits analysis_data.hidden_provisions as a write/audit snapshot.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _default_session():
    from app import db

    return db.session


def _resolve_provider_model(
    bill, full_analysis: Optional[Dict], fallback: Optional[str] = None
) -> str:
    provider_model = None
    try:
        if hasattr(bill, "get_active_ai_analysis"):
            active = bill.get_active_ai_analysis()
            if active:
                provider_model = getattr(active, "provider_model", None)
    except Exception:
        pass
    if not provider_model and isinstance(full_analysis, dict):
        provider_model = full_analysis.get("provider_model") or full_analysis.get("model")
    if not provider_model:
        provider_model = fallback
    if not provider_model:
        from utils.constants import GEMINI_MODEL

        provider_model = GEMINI_MODEL
    return provider_model


def _analysis_version(bill) -> int:
    try:
        if hasattr(bill, "get_active_ai_analysis"):
            active = bill.get_active_ai_analysis()
            if active:
                return int(getattr(active, "analysis_version", 1) or 1)
    except Exception:
        pass
    return 1


def iter_normalized_provisions(
    hidden_provisions_data: Optional[Dict],
) -> Iterable[Dict[str, Any]]:
    """
    Yield flat provision dicts from either:
    - Tier A/B flat items: {type, text, risk_level, ...}
    - Legacy wrappers: {suspicious_provisions: [...], risk_level, chunk_*}
    """
    if not isinstance(hidden_provisions_data, dict):
        return
    detected = hidden_provisions_data.get("detected_provisions") or []
    if not isinstance(detected, list):
        return

    for item in detected:
        if not isinstance(item, dict):
            continue
        nested = item.get("suspicious_provisions")
        if isinstance(nested, list) and nested:
            parent_risk = item.get("risk_level") or "low"
            parent_conf = item.get("confidence_score")
            try:
                parent_conf = float(parent_conf) if parent_conf is not None else 0.5
            except (TypeError, ValueError):
                parent_conf = 0.5
            chunk_index = item.get("chunk_index", 0)
            chunk_type = item.get("chunk_type") or "unknown"
            overall = item.get("overall_assessment") or ""
            for sp in nested:
                if not isinstance(sp, dict):
                    continue
                text = (sp.get("text") or sp.get("provision_text") or "")[:2000]
                ptype = sp.get("type") or sp.get("provision_type") or "Unknown"
                if not text and ptype == "Unknown":
                    continue
                risk = (sp.get("risk_level") or parent_risk or "low").lower()
                if risk not in ("low", "medium", "high"):
                    risk = "low"
                try:
                    conf = float(sp.get("confidence_score", parent_conf) or parent_conf)
                except (TypeError, ValueError):
                    conf = parent_conf
                yield {
                    "provision_type": ptype,
                    "provision_text": text or ptype,
                    "risk_level": risk,
                    "confidence_score": conf,
                    "potential_impact": sp.get("potential_impact") or "",
                    "recommendation": sp.get("recommendation") or "",
                    "overall_assessment": overall,
                    "chunk_index": chunk_index,
                    "chunk_type": chunk_type,
                    "risk_factors": sp.get("risk_factors")
                    if isinstance(sp.get("risk_factors"), list)
                    else [],
                }
            continue

        # Flat Tier A / Tier B / reduce shape
        text = (item.get("text") or item.get("provision_text") or "")[:2000]
        ptype = item.get("type") or item.get("provision_type") or "Unknown"
        if not text and ptype == "Unknown":
            continue
        risk = (item.get("risk_level") or "low").lower()
        if risk not in ("low", "medium", "high"):
            risk = "low"
        try:
            conf = float(item.get("confidence_score") or 0.5)
        except (TypeError, ValueError):
            conf = 0.5
        yield {
            "provision_type": ptype,
            "provision_text": text or ptype,
            "risk_level": risk,
            "confidence_score": conf,
            "potential_impact": item.get("potential_impact") or "",
            "recommendation": item.get("recommendation") or "",
            "overall_assessment": item.get("overall_assessment") or "",
            "chunk_index": item.get("chunk_index", 0),
            "chunk_type": item.get("chunk_type") or "unknown",
            "risk_factors": item.get("risk_factors")
            if isinstance(item.get("risk_factors"), list)
            else [],
        }


def store_hidden_provisions(
    bill,
    hidden_provisions_data: Optional[Dict],
    full_analysis: Optional[Dict] = None,
    *,
    replace: bool = True,
    db_session=None,
    provider_model_fallback: Optional[str] = None,
) -> int:
    """
    Replace (optional) and insert HiddenProvision rows for a bill.
    Returns number of rows stored.
    """
    from db_models import HiddenProvision

    if bill is None or getattr(bill, "id", None) is None:
        return 0

    session = db_session if db_session is not None else _default_session()
    rows = list(iter_normalized_provisions(hidden_provisions_data))
    provider_model = _resolve_provider_model(
        bill, full_analysis, fallback=provider_model_fallback
    )
    version = _analysis_version(bill)

    try:
        if replace:
            existing = (
                session.query(HiddenProvision).filter_by(bill_id=bill.id).all()
            )
            for provision in existing:
                session.delete(provision)

        stored = 0
        for row in rows:
            provision = HiddenProvision(
                bill_id=bill.id,
                provision_type=row["provision_type"],
                provision_text=row["provision_text"],
                risk_level=row["risk_level"],
                confidence_score=row["confidence_score"],
                potential_impact=row["potential_impact"],
                recommendation=row["recommendation"],
                overall_assessment=row["overall_assessment"],
                chunk_index=row["chunk_index"],
                chunk_type=row["chunk_type"],
                analysis_version=version,
                detection_method="ai_enhanced",
                provider_model=provider_model,
            )
            provision.set_risk_factors(row["risk_factors"])
            session.add(provision)
            stored += 1

        session.commit()
        ident = (
            bill.get_bill_identifier()
            if hasattr(bill, "get_bill_identifier")
            else bill.id
        )
        if stored:
            logger.info(
                f"Stored {stored} hidden provisions (sneaky riders) for {ident}"
            )
        else:
            logger.info(f"No hidden provisions to store for {ident} (table cleared)")
        return stored
    except Exception as e:
        logger.error(f"Error storing hidden provisions: {e}")
        try:
            session.rollback()
        except Exception:
            pass
        return 0


def heal_hidden_provisions_from_analysis(bill) -> int:
    """
    If the bill has analysis JSON findings but no HiddenProvision rows, persist once.
    Returns number of rows stored (0 if nothing to heal).
    """
    from db_models import HiddenProvision

    if bill is None or getattr(bill, "id", None) is None:
        return 0
    if not hasattr(bill, "get_active_ai_analysis"):
        return 0

    session = _default_session()
    existing = session.query(HiddenProvision).filter_by(bill_id=bill.id).count()
    if existing > 0:
        return 0

    active = bill.get_active_ai_analysis()
    if not active:
        return 0
    data = active.get_analysis_data() or {}
    if data.get("is_partial"):
        return 0
    hidden = data.get("hidden_provisions")
    if not isinstance(hidden, dict):
        return 0
    detected = hidden.get("detected_provisions") or []
    if not detected:
        return 0

    return store_hidden_provisions(
        bill,
        hidden,
        full_analysis=data,
        replace=True,
        db_session=session,
        provider_model_fallback=getattr(active, "provider_model", None),
    )
