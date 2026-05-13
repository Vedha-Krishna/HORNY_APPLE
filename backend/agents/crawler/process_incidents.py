import json
import os
from typing import Any, Optional, Optional, Optional, Optional, Optional, Optional, Optional, Optional, Optional

from dotenv import load_dotenv
from supabase import create_client

try:
    from orchestration12 import run_pipeline_for_1_post
except ImportError:
    from agents.crawler.orchestration12 import run_pipeline_for_1_post


load_dotenv()


def get_supabase_client() -> Any:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in environment variables.")

    return create_client(supabase_url, supabase_key)


def fetch_queued_incidents(supabase: Any, limit: Optional[int] = None) -> list[dict]:
    query = (
        supabase.table("incident_queue")
        .select("""
            incident_id,
            status,
            incidents(
                *,
                incident_analysis(*),
                incident_locations(*)
            )
        """)
        .eq("status", "cleaned")
        .order("updated_at", desc=False)
    )

    if limit is not None and limit > 0:
        query = query.limit(limit)

    response = query.execute()

    rows = []

    for queue_row in response.data or []:
        incident = queue_row.get("incidents") or {}

        analysis_data = incident.get("incident_analysis") or []
        location_data = incident.get("incident_locations") or []

        # Supabase may return related rows as list OR dict depending on relationship
        if isinstance(analysis_data, list):
            analysis = analysis_data[0] if analysis_data else {}
        else:
            analysis = analysis_data or {}

        if isinstance(location_data, list):
            location = location_data[0] if location_data else {}
        else:
            location = location_data or {}

        merged_row = {
            **incident,
            **analysis,
            **location,
            "_queue_status": queue_row.get("status"),
        }

        merged_row.pop("incident_analysis", None)
        merged_row.pop("incident_locations", None)

        rows.append(merged_row)

    return rows


def db_row_to_pipeline_input(row: dict) -> dict:
    return {
        "incident_id": row["incident_id"],
        "source_platform": row["source_platform"],
        "source_url": row["source_url"],
        "raw_text": row["raw_text"],

        "cleaned_content": row.get("cleaned_content"),
        "topic_bucket": row.get("topic_bucket"),
        "location_text": row.get("location_text"),
        "action_text": row.get("action_text"),
        "normalized_time": row.get("normalized_time"),
    }

def save_agent_messages(supabase: Any, incident_id: str, messages: list[dict]) -> None:
    rows = []

    for index, msg in enumerate(messages, start=1):
        rows.append({
            "incident_id": incident_id,
            "agent": msg.get("agent", "unknown"),
            "sequence_order": index,
            "attempt": msg.get("attempt", 1),
            "message_type": msg.get("type", "message"),
            "summary": msg.get("note") or msg.get("content"),
            "reasoning": (
                msg.get("reasoning")
                or msg.get("classifier_reasoning")
                or msg.get("decision_reason")
                or msg.get("review_of_classifier")
            ),
            "llm_raw_output": msg.get("llm_reasoning") or msg.get("content"),
            "category_assigned": msg.get("category"),
            "category_score": msg.get("category_score"),
            "authenticity_level": msg.get("authenticity_level"),
            "authenticity_score": msg.get("authenticity_score"),
            "severity_level": msg.get("severity_level"),
            "severity_score": msg.get("severity"),
            "decision_made": msg.get("decision"),
            "decision_instruction": msg.get("instruction"),
            "decision_reason": msg.get("decision_reason") or msg.get("reason"),
            "classifier_review": msg.get("review_of_classifier"),
            "metadata": msg,
        })

    if rows:
        supabase.table("incident_agent_messages").insert(rows).execute()

def update_incident_after_pipeline(supabase: Any, row_id: str, result: dict) -> None:
    location_text = result.get("location_text") or result.get("location")
    action_text = result.get("action_text") or result.get("action")

    # 1. Save classification + extracted action
    (
        supabase.table("incident_analysis")
        .upsert({
            "incident_id": row_id,
            "category": result["category"],
            "category_score": result.get("category_score"),
            "authenticity_score": result["authenticity_score"],
            "severity": result["severity"],
            "action_text": action_text,
        })
        .execute()
    )

    # 2. Save location
    if location_text or result.get("latitude") or result.get("longitude"):
        (
            supabase.table("incident_locations")
            .upsert({
                "incident_id": row_id,
                "location_text": location_text,
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
            })
            .execute()
        )

    # 3. Save final decision
    (
        supabase.table("incident_decisions")
        .upsert({
            "incident_id": row_id,
            "decision": result["decision"],
            "decision_reason": result.get("decision_reason"),
        })
        .execute()
    )

    
    save_agent_messages(
        supabase=supabase,
        incident_id=row_id,
        messages=result.get("messages", [])
    )

    # 4. Save queue status
    (
        supabase.table("incident_queue")
        .update({"status": "processed"})
        .eq("incident_id", row_id)
        .execute()
    )


def process_queued_incidents(max_incidents: Optional[int] = None) -> dict[str, int]:
    if max_incidents is not None and max_incidents <= 0:
        print("Skipping incident processing because max_incidents is 0.")
        return {"found": 0, "processed": 0, "failed": 0}

    supabase = get_supabase_client()
    rows = fetch_queued_incidents(supabase, limit=max_incidents)
    stats = {"found": len(rows), "processed": 0, "failed": 0}

    print(f"Found {len(rows)} cleaned incidents ready for classification.")

    for row in rows:
        try:
            post = db_row_to_pipeline_input(row)
            result = run_pipeline_for_1_post(post)

            print("\nAgent Conversation:\n")

            for msg in result["messages"]:
                agent = msg.get("agent", "unknown")

                if "llm_reasoning" in msg:
                    print(f"  {agent.capitalize()} (LLM):")
                    print(f"   {msg['llm_reasoning']}\n")

                elif "reasoning" in msg:
                    print(f"  {agent.capitalize()} (system):")
                    print(f"   {msg['reasoning']}\n")

                elif "instruction" in msg:
                    print(f"  {agent.capitalize()}:")
                    print(f"   {msg['instruction']}\n")

                elif "note" in msg:
                    print(f"  {agent.capitalize()}:")
                    print(f"   {msg['note']}\n")

            print("-" * 40)

            update_incident_after_pipeline(supabase, row["incident_id"], result)

            print(
                f"Processed incident id={row['incident_id']} | "
                f"decision={result['decision']} | "
                f"category={result['category']}"
            )
            stats["processed"] += 1

        except Exception as exc:
            print(f"Failed to process incident id={row.get('incident_id')}: {exc}")
            stats["failed"] += 1

    return stats


if __name__ == "__main__":
    print(process_queued_incidents())
