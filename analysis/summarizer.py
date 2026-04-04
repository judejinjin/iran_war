"""
Summarizer — Daily geopolitical and military summary generation.

Uses Claude to produce category-level daily summaries and military daily summaries.
"""

import json
from datetime import date, datetime
from loguru import logger

from config import EVENT_CATEGORIES
from db.database import (
    get_session, GeopoliticalEvent, DailySummary,
    MilitaryEvent, MilitaryDeployment, MilitaryDailySummary,
)
from agents.llm_client import get_llm_client


GEO_SUMMARY_SYSTEM = """You are an expert geopolitical analyst summarizing the day's events related to the Iran conflict and oil markets.

Given a list of classified events for a specific category, produce a concise daily summary covering:
1. Key developments
2. Escalation or de-escalation signals
3. Supply impact assessment
4. Average severity assessment

Respond with JSON:
{
    "summary_text": "2-4 sentence summary of the day's events in this category",
    "severity_avg": N.N,
    "total_supply_impact_mbd": N.N
}"""


MILITARY_SUMMARY_SYSTEM = """You are a military analyst producing a daily war summary for one side (Iran or Opposing Forces).

Given the day's military events and deployment data, produce a structured summary with:
1. Key operations and outcomes
2. Loss assessment (personnel, aircraft, naval, armor, missiles, drones)
3. Deployment status
4. Escalation score (1-10, where 1=minimal activity, 10=major escalation)

Respond with JSON:
{
    "summary_text": "2-4 sentence operational summary",
    "escalation_score": N,
    "total_personnel_losses": N,
    "total_aircraft_losses": N,
    "total_naval_losses": N,
    "total_armor_losses": N,
    "total_missile_losses": N,
    "total_drone_losses": N
}"""


def generate_daily_summaries(target_date: date = None) -> int:
    """
    Generate daily summaries for all event categories for the given date.
    Creates or updates DailySummary rows.

    Returns: number of summaries generated.
    """
    if target_date is None:
        target_date = date.today()

    session = get_session()
    client = get_llm_client()
    generated = 0

    try:
        for category in EVENT_CATEGORIES:
            events = session.query(GeopoliticalEvent).filter(
                GeopoliticalEvent.timestamp >= datetime.combine(target_date, datetime.min.time()),
                GeopoliticalEvent.timestamp < datetime.combine(target_date, datetime.max.time()),
                GeopoliticalEvent.category == category,
            ).all()

            if not events:
                continue

            # Build event list for prompt
            event_list = []
            for e in events:
                event_list.append({
                    "headline": e.headline,
                    "severity": e.severity,
                    "supply_impact_mbd": e.supply_impact_mbd,
                    "location": e.location_name,
                })

            prompt = f"""Date: {target_date}
Category: {category}
Events ({len(events)} total):
{json.dumps(event_list, indent=1)}

Produce the daily summary."""

            try:
                response = client.simple_prompt(GEO_SUMMARY_SYSTEM, prompt)
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
                result = json.loads(text)

                # Upsert daily summary
                existing = session.query(DailySummary).filter(
                    DailySummary.date == target_date,
                    DailySummary.category == category,
                ).first()

                if existing:
                    existing.summary_text = result.get("summary_text", "")
                    existing.severity_avg = result.get("severity_avg", 0)
                    existing.total_supply_impact_mbd = result.get("total_supply_impact_mbd", 0)
                else:
                    session.add(DailySummary(
                        date=target_date,
                        category=category,
                        summary_text=result.get("summary_text", ""),
                        severity_avg=result.get("severity_avg", 0),
                        total_supply_impact_mbd=result.get("total_supply_impact_mbd", 0),
                    ))

                generated += 1

            except Exception as e:
                logger.warning(f"Summary generation failed for {category}: {e}")

        session.commit()
        logger.info(f"Generated {generated} daily summaries for {target_date}")
        return generated

    except Exception as e:
        session.rollback()
        logger.error(f"Daily summary generation failed: {e}")
        raise
    finally:
        session.close()


def generate_military_daily_summary(target_date: date = None) -> int:
    """
    Generate military daily summaries for each side (Iran, Opposing) for the given date.
    Aggregates losses and deployments, generates AI summary with escalation score.

    Returns: number of summaries generated.
    """
    if target_date is None:
        target_date = date.today()

    session = get_session()
    client = get_llm_client()
    generated = 0

    try:
        for side in ["Iran", "Opposing"]:
            # Get military events for this side/date
            mil_events = session.query(MilitaryEvent).filter(
                MilitaryEvent.date == target_date,
                MilitaryEvent.side == side,
            ).all()

            # Get deployments for this side/date
            deployments = session.query(MilitaryDeployment).filter(
                MilitaryDeployment.date == target_date,
                MilitaryDeployment.side == side,
            ).all()

            if not mil_events and not deployments:
                continue

            # Build prompt data
            events_data = [
                {
                    "event_type": e.event_type,
                    "loss_type": e.loss_type,
                    "quantity": e.quantity,
                    "unit_name": e.unit_name,
                    "equipment": e.equipment_detail,
                    "headline": e.headline,
                    "location": e.location_name,
                }
                for e in mil_events
            ]

            deploy_data = [
                {
                    "status": d.deployment_status,
                    "force_type": d.force_type,
                    "unit": d.unit_name,
                    "personnel": d.personnel_count,
                    "equipment": d.equipment_summary,
                    "region": d.region,
                }
                for d in deployments
            ]

            prompt = f"""Date: {target_date}
Side: {side}

Military Events ({len(mil_events)}):
{json.dumps(events_data, indent=1)}

Deployments ({len(deployments)}):
{json.dumps(deploy_data, indent=1)}

Produce the military daily summary."""

            try:
                response = client.simple_prompt(MILITARY_SUMMARY_SYSTEM, prompt)
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
                result = json.loads(text)

                # Compute cumulative losses from previous day
                prev_summary = session.query(MilitaryDailySummary).filter(
                    MilitaryDailySummary.date < target_date,
                    MilitaryDailySummary.side == side,
                ).order_by(MilitaryDailySummary.date.desc()).first()

                cum_personnel = (prev_summary.cumulative_personnel_losses if prev_summary else 0) + result.get("total_personnel_losses", 0)
                cum_aircraft = (prev_summary.cumulative_aircraft_losses if prev_summary else 0) + result.get("total_aircraft_losses", 0)
                cum_naval = (prev_summary.cumulative_naval_losses if prev_summary else 0) + result.get("total_naval_losses", 0)

                # Deployment counts
                active_deployed = sum(d.personnel_count or 0 for d in deployments if d.deployment_status == "active")
                pending_deployed = sum(d.personnel_count or 0 for d in deployments if d.deployment_status == "pending")

                # Upsert
                existing = session.query(MilitaryDailySummary).filter(
                    MilitaryDailySummary.date == target_date,
                    MilitaryDailySummary.side == side,
                ).first()

                summary_data = {
                    "total_personnel_losses": result.get("total_personnel_losses", 0),
                    "total_aircraft_losses": result.get("total_aircraft_losses", 0),
                    "total_naval_losses": result.get("total_naval_losses", 0),
                    "total_armor_losses": result.get("total_armor_losses", 0),
                    "total_missile_losses": result.get("total_missile_losses", 0),
                    "total_drone_losses": result.get("total_drone_losses", 0),
                    "cumulative_personnel_losses": cum_personnel,
                    "cumulative_aircraft_losses": cum_aircraft,
                    "cumulative_naval_losses": cum_naval,
                    "active_personnel_deployed": active_deployed,
                    "pending_personnel_deployment": pending_deployed,
                    "summary_text": result.get("summary_text", ""),
                    "escalation_score": max(1, min(10, result.get("escalation_score", 5))),
                }

                if existing:
                    for key, val in summary_data.items():
                        setattr(existing, key, val)
                else:
                    session.add(MilitaryDailySummary(
                        date=target_date,
                        side=side,
                        **summary_data,
                    ))

                generated += 1

            except Exception as e:
                logger.warning(f"Military summary failed for {side}: {e}")

        session.commit()
        logger.info(f"Generated {generated} military daily summaries for {target_date}")
        return generated

    except Exception as e:
        session.rollback()
        logger.error(f"Military summary generation failed: {e}")
        raise
    finally:
        session.close()


def run_all_summaries(target_date: date = None) -> dict:
    """Run both geopolitical and military daily summaries."""
    if target_date is None:
        target_date = date.today()

    geo_count = generate_daily_summaries(target_date)
    mil_count = generate_military_daily_summary(target_date)

    return {"geopolitical_summaries": geo_count, "military_summaries": mil_count}
