"""Unified weekly metrics service."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session, sessionmaker

from extensions import db
from utils import calculate_quarter_revenue, get_next_quarter_dates, get_quarter_dates


TRACKED_MODELS = {"SalesLead", "Pipeline"}


def get_week_start(ref_date: date | None = None) -> date:
    ref_date = ref_date or date.today()
    return ref_date - timedelta(days=ref_date.weekday())


def get_last_week_start(ref_date: date | None = None) -> date:
    return get_week_start(ref_date) - timedelta(weeks=1)


def _get_session_factory():
    return sessionmaker(bind=db.engine, expire_on_commit=False)


def _normalize_owner_ids(owner_ids: Iterable[int | None] | None) -> list[int]:
    normalized = []
    for owner_id in owner_ids or []:
        if owner_id:
            normalized.append(int(owner_id))
    return sorted(set(normalized))


def _tracked_owner_ids(obj) -> set[int]:
    owner_ids = set()

    if obj.__class__.__name__ not in TRACKED_MODELS:
        return owner_ids

    current_owner_id = getattr(obj, "owner_id", None)
    if current_owner_id:
        owner_ids.add(int(current_owner_id))

    try:
        history = sa_inspect(obj).attrs.owner_id.history
    except Exception:
        history = None

    if history:
        for owner_id in list(history.added) + list(history.deleted):
            if owner_id:
                owner_ids.add(int(owner_id))

    return owner_ids


def _get_or_create_record(session: Session, owner_id: int | None, week_start: date):
    record = (
        session.query(_get_models()["WeeklyMetrics"])
        .filter_by(owner_id=owner_id, week_start=week_start)
        .order_by(_get_models()["WeeklyMetrics"].id.asc())
        .first()
    )
    if record is None:
        record = _get_models()["WeeklyMetrics"](owner_id=owner_id, week_start=week_start)
        session.add(record)
        session.flush()
    return record


def _get_models():
    from models import Pipeline, SalesLead, User, WeeklyMetrics

    return {
        "Pipeline": Pipeline,
        "SalesLead": SalesLead,
        "User": User,
        "WeeklyMetrics": WeeklyMetrics,
    }


def compute_owner_metrics(owner_id: int, session: Session, ref_date: date | None = None) -> dict:
    models = _get_models()
    Pipeline = models["Pipeline"]
    SalesLead = models["SalesLead"]

    ref_date = ref_date or date.today()
    current_qtr = get_quarter_dates(ref_date)
    next_qtr = get_next_quarter_dates(ref_date)

    pipelines = (
        session.query(Pipeline)
        .filter(
            Pipeline.owner_id == owner_id,
            Pipeline.stage != "6b) Deal Lost",
        )
        .all()
    )

    leads_count = (
        session.query(SalesLead)
        .filter(
            SalesLead.owner_id == owner_id,
            SalesLead.leads_status != "Unqualified",
        )
        .count()
    )

    qualified_leads_count = (
        session.query(SalesLead)
        .filter(
            SalesLead.owner_id == owner_id,
            SalesLead.leads_status == "Qualified",
        )
        .count()
    )

    return {
        "leads_count": int(leads_count),
        "qualified_leads_count": int(qualified_leads_count),
        "pipeline_count": len(pipelines),
        "customer_count": len({pipeline.company for pipeline in pipelines if pipeline.company}),
        "tcv": int(sum((pipeline.tcv_usd or 0) for pipeline in pipelines)),
        "current_qtr_revenue": int(calculate_quarter_revenue(pipelines, current_qtr[0], current_qtr[1])),
        "next_qtr_revenue": int(calculate_quarter_revenue(pipelines, next_qtr[0], next_qtr[1])),
    }


def compute_company_metrics(session: Session, ref_date: date | None = None) -> dict:
    models = _get_models()
    Pipeline = models["Pipeline"]
    SalesLead = models["SalesLead"]

    ref_date = ref_date or date.today()
    current_qtr = get_quarter_dates(ref_date)
    next_qtr = get_next_quarter_dates(ref_date)

    pipelines = session.query(Pipeline).filter(Pipeline.stage != "6b) Deal Lost").all()

    leads_count = session.query(SalesLead).filter(SalesLead.leads_status != "Unqualified").count()
    qualified_leads_count = session.query(SalesLead).filter(SalesLead.leads_status == "Qualified").count()

    return {
        "leads_count": int(leads_count),
        "qualified_leads_count": int(qualified_leads_count),
        "pipeline_count": len(pipelines),
        "tcv": int(sum((pipeline.tcv_usd or 0) for pipeline in pipelines)),
        "current_qtr_revenue": int(calculate_quarter_revenue(pipelines, current_qtr[0], current_qtr[1])),
        "next_qtr_revenue": int(calculate_quarter_revenue(pipelines, next_qtr[0], next_qtr[1])),
    }


def _apply_metric_values(record, metrics: dict, previous_record=None):
    record.leads_count = metrics["leads_count"]
    record.qualified_leads_count = metrics["qualified_leads_count"]
    record.pipeline_count = metrics["pipeline_count"]
    record.tcv = metrics["tcv"]
    record.current_qtr_revenue = metrics["current_qtr_revenue"]
    record.next_qtr_revenue = metrics["next_qtr_revenue"]

    previous_record = previous_record or {}
    record.leads_vs_last_week = metrics["leads_count"] - int(getattr(previous_record, "leads_count", 0) or 0)
    record.qualified_vs_last_week = metrics["qualified_leads_count"] - int(getattr(previous_record, "qualified_leads_count", 0) or 0)
    record.pipeline_vs_last_week = metrics["pipeline_count"] - int(getattr(previous_record, "pipeline_count", 0) or 0)
    record.tcv_vs_last_week = metrics["tcv"] - int(getattr(previous_record, "tcv", 0) or 0)

    record.leads_vs_last_month = 0
    record.qualified_vs_last_month = 0
    record.pipeline_vs_last_month = 0
    record.tcv_vs_last_month = 0
    record.updated_at = datetime.utcnow()


def refresh_weekly_metrics(owner_ids: Iterable[int] | None = None, ref_date: date | None = None) -> None:
    models = _get_models()
    User = models["User"]
    WeeklyMetrics = models["WeeklyMetrics"]

    ref_date = ref_date or date.today()
    week_start = get_week_start(ref_date)
    last_week_start = get_last_week_start(ref_date)
    owner_ids = _normalize_owner_ids(owner_ids)

    session_factory = _get_session_factory()
    session = session_factory()

    try:
        if not owner_ids:
            owner_ids = [
                user.id
                for user in session.query(User).filter_by(is_active=True).all()
            ]

        for owner_id in owner_ids:
            metrics = compute_owner_metrics(owner_id, session=session, ref_date=ref_date)
            previous_record = (
                session.query(WeeklyMetrics)
                .filter_by(owner_id=owner_id, week_start=last_week_start)
                .first()
            )
            record = _get_or_create_record(session, owner_id, week_start)
            _apply_metric_values(record, metrics, previous_record=previous_record)

        company_metrics = compute_company_metrics(session=session, ref_date=ref_date)
        previous_company_record = (
            session.query(WeeklyMetrics)
            .filter_by(owner_id=None, week_start=last_week_start)
            .order_by(WeeklyMetrics.id.asc())
            .first()
        )
        company_record = _get_or_create_record(session, None, week_start)
        _apply_metric_values(company_record, company_metrics, previous_record=previous_company_record)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_current_week_snapshots(ref_date: date | None = None) -> None:
    models = _get_models()
    User = models["User"]
    WeeklyMetrics = models["WeeklyMetrics"]

    ref_date = ref_date or date.today()
    week_start = get_week_start(ref_date)

    active_owner_ids = [user.id for user in User.query.filter_by(is_active=True).all()]
    existing_owner_ids = {
        owner_id
        for (owner_id,) in db.session.query(WeeklyMetrics.owner_id)
        .filter(WeeklyMetrics.week_start == week_start, WeeklyMetrics.owner_id.isnot(None))
        .all()
    }
    missing_owner_ids = [owner_id for owner_id in active_owner_ids if owner_id not in existing_owner_ids]

    company_exists = (
        db.session.query(WeeklyMetrics.id)
        .filter_by(owner_id=None, week_start=week_start)
        .first()
        is not None
    )

    if missing_owner_ids or not company_exists:
        refresh_weekly_metrics(owner_ids=active_owner_ids, ref_date=ref_date)


def build_summary_metric(current_value: int | float, previous_value: int | float) -> dict:
    delta = current_value - previous_value
    pct = None if previous_value == 0 else (delta / previous_value) * 100
    return {
        "current": current_value,
        "previous": previous_value,
        "delta": delta,
        "pct": pct,
    }


def get_company_dashboard_summary(ref_date: date | None = None) -> dict:
    models = _get_models()
    WeeklyMetrics = models["WeeklyMetrics"]

    ref_date = ref_date or date.today()
    week_start = get_week_start(ref_date)
    last_week_start = get_last_week_start(ref_date)

    ensure_current_week_snapshots(ref_date=ref_date)

    current_record = (
        WeeklyMetrics.query.filter_by(owner_id=None, week_start=week_start)
        .order_by(WeeklyMetrics.id.asc())
        .first()
    )
    previous_record = (
        WeeklyMetrics.query.filter_by(owner_id=None, week_start=last_week_start)
        .order_by(WeeklyMetrics.id.asc())
        .first()
    )

    current_record = current_record or WeeklyMetrics(owner_id=None, week_start=week_start)
    previous_record = previous_record or WeeklyMetrics(owner_id=None, week_start=last_week_start)

    return {
        "leads": build_summary_metric(current_record.leads_count or 0, previous_record.leads_count or 0),
        "qualified": build_summary_metric(current_record.qualified_leads_count or 0, previous_record.qualified_leads_count or 0),
        "pipeline": build_summary_metric(current_record.pipeline_count or 0, previous_record.pipeline_count or 0),
        "tcv": build_summary_metric(current_record.tcv or 0, previous_record.tcv or 0),
        "current_qtr_revenue": build_summary_metric(current_record.current_qtr_revenue or 0, previous_record.current_qtr_revenue or 0),
        "next_qtr_revenue": build_summary_metric(current_record.next_qtr_revenue or 0, previous_record.next_qtr_revenue or 0),
    }


def get_owner_dashboard_summary(owner_id: int, ref_date: date | None = None) -> dict:
    models = _get_models()
    WeeklyMetrics = models["WeeklyMetrics"]

    ref_date = ref_date or date.today()
    week_start = get_week_start(ref_date)
    last_week_start = get_last_week_start(ref_date)

    ensure_current_week_snapshots(ref_date=ref_date)

    current_record = (
        WeeklyMetrics.query.filter_by(owner_id=owner_id, week_start=week_start)
        .order_by(WeeklyMetrics.id.asc())
        .first()
    )
    previous_record = (
        WeeklyMetrics.query.filter_by(owner_id=owner_id, week_start=last_week_start)
        .order_by(WeeklyMetrics.id.asc())
        .first()
    )

    current_record = current_record or WeeklyMetrics(owner_id=owner_id, week_start=week_start)
    previous_record = previous_record or WeeklyMetrics(owner_id=owner_id, week_start=last_week_start)

    return {
        "leads": build_summary_metric(current_record.leads_count or 0, previous_record.leads_count or 0),
        "qualified": build_summary_metric(current_record.qualified_leads_count or 0, previous_record.qualified_leads_count or 0),
        "pipeline": build_summary_metric(current_record.pipeline_count or 0, previous_record.pipeline_count or 0),
        "tcv": build_summary_metric(current_record.tcv or 0, previous_record.tcv or 0),
        "current_qtr_revenue": build_summary_metric(current_record.current_qtr_revenue or 0, previous_record.current_qtr_revenue or 0),
        "next_qtr_revenue": build_summary_metric(current_record.next_qtr_revenue or 0, previous_record.next_qtr_revenue or 0),
    }


def get_owner_dashboard_metrics(ref_date: date | None = None) -> list[dict]:
    models = _get_models()
    User = models["User"]
    WeeklyMetrics = models["WeeklyMetrics"]

    ref_date = ref_date or date.today()
    week_start = get_week_start(ref_date)

    ensure_current_week_snapshots(ref_date=ref_date)

    users = User.query.filter_by(is_active=True).all()
    records = {
        record.owner_id: record
        for record in WeeklyMetrics.query.filter(
            WeeklyMetrics.week_start == week_start,
            WeeklyMetrics.owner_id.isnot(None),
        ).all()
    }

    metrics = []
    for user in users:
        record = records.get(user.id) or WeeklyMetrics(owner_id=user.id, week_start=week_start)
        metrics.append({
            "user": user,
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "leads_count": int(record.leads_count or 0),
            "qualified_leads_count": int(record.qualified_leads_count or 0),
            "pipeline_count": int(record.pipeline_count or 0),
            "customer_count": compute_owner_metrics(user.id, session=db.session, ref_date=ref_date)["customer_count"],
            "tcv": int(record.tcv or 0),
            "current_qtr_revenue": int(record.current_qtr_revenue or 0),
            "next_qtr_revenue": int(record.next_qtr_revenue or 0),
        })

    metrics.sort(key=lambda item: item["tcv"], reverse=True)
    return metrics


def register_weekly_metrics_hooks(app) -> None:
    if app.extensions.get("weekly_metrics_hooks_registered"):
        return

    from models import metrics_events_disabled

    @event.listens_for(db.session, "before_flush")
    def collect_weekly_metrics_changes(session, flush_context, instances):
        if metrics_events_disabled():
            session.info.pop("weekly_metrics_owner_ids", None)
            return

        owner_ids = set(session.info.get("weekly_metrics_owner_ids", set()))
        for collection in (session.new, session.dirty, session.deleted):
            for obj in collection:
                owner_ids.update(_tracked_owner_ids(obj))
        if owner_ids:
            session.info["weekly_metrics_owner_ids"] = owner_ids

    @event.listens_for(db.session, "after_commit")
    def refresh_weekly_metrics_after_commit(session):
        owner_ids = session.info.pop("weekly_metrics_owner_ids", set())
        if not owner_ids:
            return
        try:
            refresh_weekly_metrics(owner_ids=owner_ids)
        except Exception as exc:
            app.logger.warning("Failed to refresh weekly metrics for %s: %s", sorted(owner_ids), exc)

    @event.listens_for(db.session, "after_rollback")
    def clear_weekly_metrics_changes(session):
        session.info.pop("weekly_metrics_owner_ids", None)

    app.extensions["weekly_metrics_hooks_registered"] = True
