import json
from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END

from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# =========================================================
# 1. CATEGORY LIST + BACKWARD-COMPATIBLE SCORE MAPS
# =========================================================
VALID_CATEGORIES = [
    "theft",
    "burglary",
    "robbery",
    "assault",
    "violent_crime",
    "vandalism",
    "scam_fraud",
    "identity_document_fraud",
    "harassment_threat",
    "sexual_offense",
    "suspicious_activity",
    "public_disorder",
    "regulatory_offence",
    "drug_offence",
    "traffic_transport_offence",
    "other",
]

VALID_AUTHENTICITY = ["low", "medium", "high"]
VALID_SEVERITY = ["low", "medium", "high"]
VALID_DECISIONS = ["publish", "needs_retry", "reject"]

# Temporary compatibility with old DB/dashboard fields.
AUTHENTICITY_MAP = {
    "low": 0.20,
    "medium": 0.55,
    "high": 0.80,
}

SEVERITY_MAP = {
    "low": 0.25,
    "medium": 0.60,
    "high": 0.90,
}

CATEGORY_SCORE_MAP = {
    "other": 0.00,
    "theft": 0.85,
    "burglary": 0.85,
    "robbery": 0.85,
    "assault": 0.85,
    "violent_crime": 0.85,
    "vandalism": 0.85,
    "scam_fraud": 0.85,
    "identity_document_fraud": 0.85,
    "harassment_threat": 0.85,
    "sexual_offense": 0.85,
    "suspicious_activity": 0.75,
    "public_disorder": 0.80,
    "regulatory_offence": 0.80,
    "drug_offence": 0.85,
    "traffic_transport_offence": 0.80,
}


# =========================================================
# 2. SHARED STATE
# =========================================================
class State(TypedDict):
    # Raw source fields
    incident_id: int
    source_platform: str
    source_url: str
    raw_text: str

    # Cleaner fields
    cleaned_content: Optional[str]
    topic_bucket: Optional[str]
    location_text: Optional[str]
    action_text: Optional[str]
    normalized_time: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    # LLM-rubric classifier fields
    category: Optional[str]
    authenticity_level: Optional[str]
    severity_level: Optional[str]
    classifier_reasoning: Optional[str]

    # Old numeric fields kept for DB/dashboard compatibility
    category_score: Optional[float]
    authenticity_score: Optional[float]
    severity: Optional[float]

    # Decision fields
    decision: Optional[str]
    decision_reason: Optional[str]

    # Runtime fields
    messages: List[dict]
    retry_count: int


# =========================================================
# 3. HELPERS
# =========================================================
def clean_json_response(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


def safe_json_loads(raw: str, fallback: dict) -> dict:
    try:
        parsed = json.loads(clean_json_response(raw))
        if isinstance(parsed, dict):
            return parsed
        return fallback
    except json.JSONDecodeError:
        return fallback


def call_llm_json(prompt: str, model: str = "gpt-4o-mini", fallback: Optional[dict] = None) -> dict:
    if fallback is None:
        fallback = {}

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return fallback

    raw = response.choices[0].message.content or ""
    return safe_json_loads(raw, fallback)


def is_valid_category(category: Optional[str]) -> bool:
    return category in VALID_CATEGORIES


def is_valid_level(level: Optional[str], valid_levels: List[str]) -> bool:
    return level in valid_levels


def level_to_authenticity_score(level: Optional[str]) -> float:
    return AUTHENTICITY_MAP.get(level or "low", 0.20)


def level_to_severity_score(level: Optional[str]) -> float:
    return SEVERITY_MAP.get(level or "low", 0.25)


def category_to_score(category: Optional[str]) -> float:
    return CATEGORY_SCORE_MAP.get(category or "other", 0.00)


def has_some_core_incident_signal(state: State) -> bool:
    """
    Softer than requiring both location and action.
    This avoids rejecting real incidents just because extraction missed one field.
    """
    return bool(state.get("location_text")) or bool(state.get("action_text"))


def build_classifier_message(
    attempt: int,
    category: str,
    category_score: float,
    authenticity_level: str,
    authenticity_score: float,
    severity_level: str,
    severity: float,
    classifier_reasoning: str,
) -> dict:
    """
    This message is intentionally redundant.
    - structured fields are useful for DB/frontend components
    - content/note/reasoning are useful for simple website renderers
    """
    content = (
        f"Category: {category}\n"
        f"Category Score: {category_score}\n"
        f"Authenticity: {authenticity_level} ({authenticity_score})\n"
        f"Severity: {severity_level} ({severity})\n"
        f"Reasoning: {classifier_reasoning}"
    )

    return {
        "agent": "classifier",
        "type": "classification_result",
        "attempt": attempt,

        # structured fields
        "category": category,
        "category_score": category_score,
        "authenticity_level": authenticity_level,
        "authenticity_score": authenticity_score,
        "severity_level": severity_level,
        "severity": severity,
        "classifier_reasoning": classifier_reasoning,

        # website-friendly fallback fields
        "content": content,
        "note": (
            f"Classified as {category}. "
            f"Authenticity: {authenticity_level} ({authenticity_score}). "
            f"Severity: {severity_level} ({severity})."
        ),
        "reasoning": classifier_reasoning,
        "llm_reasoning": content,
    }


def build_decision_message(
    attempt: int,
    decision: str,
    instruction: str,
    decision_reason: str,
    review_of_classifier: str,
) -> dict:
    content = (
        f"Decision: {decision}\n"
        f"Instruction: {instruction}\n"
        f"Reason: {decision_reason}\n"
        f"Review of Classifier: {review_of_classifier}"
    )

    return {
        "agent": "decision_agent",
        "type": "decision_result",
        "attempt": attempt,
        "decision": decision,
        "instruction": instruction,
        "decision_reason": decision_reason,
        "review_of_classifier": review_of_classifier,

        # website-friendly fallback fields
        "content": content,
        "note": f"Decision: {decision}",
        "reasoning": review_of_classifier,
    }


# =========================================================
# 4. CRAWLER NODE
# =========================================================
def crawler_node(state: State) -> dict:
    # This is still a mock crawler. Your real Reddit crawler can replace this.
    state["source_platform"] = state.get("source_platform") or "mock_Reddit"
    state["source_url"] = state.get("source_url") or "mock_reddit.com"

    state["messages"].append({
        "agent": "crawler",
        "type": "crawler_result",
        "source_platform": state.get("source_platform"),
        "source_url": state.get("source_url"),
        "content": "Crawler passed source post into the pipeline.",
        "note": "Crawler passed source post into the pipeline.",
    })

    state["messages"].append({
        "agent": "cleaner",
        "type": "cleaner_result",
        "source_platform": state.get("source_platform"),
        "source_url": state.get("source_url"),
        "content": "Cleaner cleaned and formatted data for better classification",
        "note": "Cleaner cleaned and formatted data for better classification",
    })

    return state


# =========================================================
# 5. CLASSIFIER NODE
# =========================================================
def classifier_node(state: State) -> dict:
    cleaned_content = state.get("cleaned_content")
    attempt = state["retry_count"] + 1

    if not cleaned_content:
        raise ValueError("Classifier received incident without cleaned_content")

    # HARD GATE: cleaner already marked it unrelated.
    if state.get("topic_bucket") == "other":
        category = "other"
        authenticity_level = "low"
        severity_level = "low"
        classifier_reasoning = "Cleaner marked this as unrelated or insufficiently relevant."
        category_score = category_to_score(category)
        authenticity_score = level_to_authenticity_score(authenticity_level)
        severity = level_to_severity_score(severity_level)

        state["messages"].append(build_classifier_message(
            attempt,
            category,
            category_score,
            authenticity_level,
            authenticity_score,
            severity_level,
            severity,
            classifier_reasoning,
        ))

        return {
            "category": category,
            "authenticity_level": authenticity_level,
            "severity_level": severity_level,
            "classifier_reasoning": classifier_reasoning,
            "category_score": category_score,
            "authenticity_score": authenticity_score,
            "severity": severity,
            "decision": "reject",
            "messages": state["messages"],
        }

    feedback_msgs = [
        m for m in state["messages"]
        if m.get("feedback_to") == "classifier"
    ]

    prompt = f"""
You are a strict Singapore incident classifier.

Classify the post using rubric-based judgement, not mathematical scoring.

Cleaned post:
{cleaned_content}

Extracted fields:
location={state.get("location_text")}
time={state.get("normalized_time")}
action={state.get("action_text")}
topic_bucket={state.get("topic_bucket")}

Previous feedback from Decision Agent:
{feedback_msgs}

If feedback is provided:
- wrong_category: reconsider the category carefully and choose a better category if needed.
- improve_evidence: re-check whether location, time, action, victim/object, or incident details were missed.
- reassess_severity: reconsider whether severity should be low, medium, or high.

Choose category from this list only:
{VALID_CATEGORIES}

Authenticity rubric:
- high: concrete location, clear action, and time/context are present; internally consistent and believable
- medium: relevant incident with a clear action, but missing location, time, or important context
- low: vague, rumor-like, contradictory, unrelated, or lacks a clear incident action

Severity rubric:
- high: physical harm, weapon, major financial loss, vulnerable victim, serious public safety risk
- medium: clear crime/disorder with some harm, threat, loss, or disruption
- low: minor issue, unclear harm, suspicious but not directly dangerous

Important rules:
- Use "other" for non-incident news, business/legal/political/trend articles, celebrity news, or general discussion.
- Use "other" for overseas incidents unless the incident happened in Singapore or creates direct Singapore public-safety risk.
- Do not force a crime category if the post is not a concrete local incident.
- Community reports do not need police reports, media, or multiple witnesses if location/action/time are coherent.
- Suspicious activity can be valid if it describes a concrete public-safety concern.
- Lost item reports should be "other" unless there is evidence of theft, scam, or suspicious activity.
- Do not claim location/time exists if it was not provided.
- Do not treat article publication date as incident time unless the incident time is explicitly stated.
- For regulatory_offence, publishability should depend on whether there is concrete enforcement action such as a fine, arrest, charge, conviction, or official action.

Return ONLY JSON:
{{
  "category": "...",
  "authenticity_level": "low | medium | high",
  "severity_level": "low | medium | high",
  "classifier_reasoning": "..."
}}
"""

    fallback = {
        "category": "other",
        "authenticity_level": "low",
        "severity_level": "low",
        "classifier_reasoning": "LLM classifier output failed; fallback classification used.",
    }

    result = call_llm_json(prompt, model="gpt-4o-mini", fallback=fallback)

    category = result.get("category")
    authenticity_level = result.get("authenticity_level")
    severity_level = result.get("severity_level")
    classifier_reasoning = result.get("classifier_reasoning", "No reasoning provided.")

    # Validation fallback
    if not is_valid_category(category):
        category = "other"

    if not is_valid_level(authenticity_level, VALID_AUTHENTICITY):
        authenticity_level = "low"

    if not is_valid_level(severity_level, VALID_SEVERITY):
        severity_level = "low"

    category_score = category_to_score(category)
    authenticity_score = level_to_authenticity_score(authenticity_level)
    severity = level_to_severity_score(severity_level)

    state["messages"].append(build_classifier_message(
        attempt,
        category,
        category_score,
        authenticity_level,
        authenticity_score,
        severity_level,
        severity,
        classifier_reasoning,
    ))

    return {
        "category": category,
        "authenticity_level": authenticity_level,
        "severity_level": severity_level,
        "classifier_reasoning": classifier_reasoning,
        "category_score": category_score,
        "authenticity_score": authenticity_score,
        "severity": severity,
        "messages": state["messages"],
    }


# =========================================================
# 6. DECISION NODE
# =========================================================
def decision_node(state: State) -> dict:
    attempt = state["retry_count"] + 1

    # HARD REJECT: non-incident category.
    if state.get("category") == "other":
        decision = "reject"
        decision_reason = "Rejected because classifier categorized this as other / non-incident."
        instruction = "no_retry"
        review_of_classifier = "Decision Agent agrees with the classifier that this should not be published as a crime/public-safety incident."

        state["decision"] = decision
        state["decision_reason"] = decision_reason
        state["messages"].append(build_decision_message(attempt, decision, instruction, decision_reason, review_of_classifier))
        return state

    # SOFT HARD-GATE: reject only if cleaner found no core signal AND classifier is not confident.
    if not has_some_core_incident_signal(state) and state.get("authenticity_level") != "high":
        decision = "reject"
        decision_reason = (
            "Rejected because the post does not contain enough core incident details "
            "and classifier confidence is not high."
        )
        instruction = "no_retry"
        review_of_classifier = "Decision Agent rejected after reviewing classifier output and missing extracted incident signals."

        state["decision"] = decision
        state["decision_reason"] = decision_reason
        state["messages"].append(build_decision_message(attempt, decision, instruction, decision_reason, review_of_classifier))
        return state

    # HARD RETRY LIMIT.
    if state["retry_count"] >= 2:
        decision = "reject"
        decision_reason = "Retry limit reached. Rejecting to prevent repeated classifier loops."
        instruction = "no_retry"
        review_of_classifier = "Decision Agent stopped the loop after too many attempts."

        state["decision"] = decision
        state["decision_reason"] = decision_reason
        state["messages"].append(build_decision_message(attempt, decision, instruction, decision_reason, review_of_classifier))
        return state

    prompt = f"""
You are the final decision agent for a Singapore community incident pipeline.

Review the Classifier Agent's output and decide one of:
- publish
- needs_retry
- reject

Classifier Agent output:
category={state.get("category")}
category_score={state.get("category_score")}
authenticity_level={state.get("authenticity_level")}
authenticity_score={state.get("authenticity_score")}
severity_level={state.get("severity_level")}
severity={state.get("severity")}
classifier_reasoning={state.get("classifier_reasoning")}

Incident data:
cleaned_content={state.get("cleaned_content")}
location={state.get("location_text")}
time={state.get("normalized_time")}
action={state.get("action_text")}
retry_count={state.get("retry_count")}

Decision rules:
Decision rules:

Publish ONLY if the post describes a concrete Singapore incident with at least TWO of:
- clear offence/safety action
- clear target/victim/object
- clear Singapore location
- clear time/context
- credible risk to public safety, property, or personal safety

Publish if it is a concrete local report involving:
- theft, scam/fraud, assault, harassment/threat, sexual offence, drug offence, weapon/firearm risk, suspicious activity with clear risky action, or public disorder with specific details.

Reject if it is:
- general news, political/legal/business commentary, corporate updates, celebrity/family drama, trend discussion, or viral content
- a regulatory/business/legal article without direct public-safety risk
- a lost item report without evidence of theft, scam, or suspicious activity
- an overseas incident without direct Singapore public-safety relevance
- vague suspicion with no clear action, target, victim, threat, or attempted offence
- merely “someone looked suspicious” without concrete behaviour

For suspicious_activity:
- Publish only if there is a concrete risky behaviour, such as checking car doors, following/stalking someone, carrying a weapon, soliciting money deceptively, trespassing, or attempting to access property.
- Reject vague suspicious feelings without a concrete action.

For regulatory_offence:
- Publish only if it involves direct public safety, serious enforcement action, or risk to people.
- Reject ordinary business/legal/regulatory news that is not useful as a community safety alert.

Retry rules:
- Use needs_retry only if the post is probably relevant but the classifier made a clear mistake.
- Do not use repeated retries for vague posts.
- If details are still vague after one retry, reject.
Return ONLY JSON:
{{
  "decision": "publish | needs_retry | reject",
  "decision_reason": "...",
  "instruction": "wrong_category | improve_evidence | no_retry",
  "review_of_classifier": "Explain whether you agree or disagree with the classifier's category/authenticity/severity judgement."
}}
"""

    fallback = {
        "decision": "reject",
        "decision_reason": "LLM decision output failed; fallback reject used.",
        "instruction": "no_retry",
        "review_of_classifier": "Decision Agent could not parse the LLM output.",
    }

    result = call_llm_json(prompt, model="gpt-4o-mini", fallback=fallback)

    decision = result.get("decision")
    decision_reason = result.get("decision_reason", "No reason provided.")
    instruction = result.get("instruction", "no_retry")
    review_of_classifier = result.get("review_of_classifier", "No classifier review provided.")

    if decision not in VALID_DECISIONS:
        decision = "reject"
        decision_reason = "Invalid decision value returned; fallback reject used."
        instruction = "no_retry"
        review_of_classifier = "Decision Agent rejected because the decision value was invalid."

    state["decision"] = decision
    state["decision_reason"] = decision_reason

    # If retry, add explicit feedback that classifier can read on next attempt.
    if decision == "needs_retry":
        state["retry_count"] += 1

        state["messages"].append({
            "agent": "decision_agent",
            "type": "classifier_feedback",
            "feedback_to": "classifier",
            "attempt": attempt,
            "instruction": instruction,
            "reason": decision_reason,
            "review_of_classifier": review_of_classifier,
            "content": (
                f"Feedback to Classifier: {instruction}\n"
                f"Reason: {decision_reason}\n"
                f"Review: {review_of_classifier}"
            ),
            "note": f"Feedback to classifier: {instruction}",
            "reasoning": review_of_classifier,
        })

    state["messages"].append(build_decision_message(attempt, decision, instruction, decision_reason, review_of_classifier))

    print("DEBUG retry_count:", state["retry_count"])
    print("DEBUG current decision state:", state.get("decision"))

    return state


# =========================================================
# 7. CONDITIONAL EDGE ROUTER
# =========================================================
def edge_after_decision(state: State):
    if state["decision"] == "needs_retry":
        return "classifier"
    return END


# =========================================================
# 8. BUILD GRAPH
# =========================================================
graph_builder = StateGraph(State)

graph_builder.add_node("crawler", crawler_node)
graph_builder.add_node("classifier", classifier_node)
graph_builder.add_node("decision", decision_node)

graph_builder.add_edge(START, "crawler")
graph_builder.add_edge("crawler", "classifier")
graph_builder.add_edge("classifier", "decision")
graph_builder.add_conditional_edges("decision", edge_after_decision)

graph = graph_builder.compile()


# =========================================================
# 9. PREPARE INITIAL STATE
# =========================================================
def prepare_initial_state(post: dict) -> State:
    return {
        "incident_id": post["incident_id"],
        "source_platform": post.get("source_platform", "mock_Reddit"),
        "source_url": post.get("source_url", "mock_reddit.com"),
        "raw_text": post["raw_text"],

        # cleaner output fields
        "cleaned_content": post.get("cleaned_content"),
        "topic_bucket": post.get("topic_bucket"),
        "location_text": post.get("location_text"),
        "action_text": post.get("action_text"),
        "latitude": post.get("latitude"),
        "longitude": post.get("longitude"),
        "normalized_time": post.get("normalized_time"),

        # classifier output fields
        "category": None,
        "authenticity_level": None,
        "severity_level": None,
        "classifier_reasoning": None,

        # old compatibility fields
        "category_score": None,
        "authenticity_score": None,
        "severity": None,

        # decision output fields
        "decision": None,
        "decision_reason": None,

        # runtime fields
        "messages": [],
        "retry_count": 0,
    }


# =========================================================
# 10. RUN PIPELINE
# =========================================================
def run_pipeline_for_1_post(post: dict) -> State:
    state = prepare_initial_state(post)
    result = graph.invoke(state)
    return result


# =========================================================
# 11. PRINTING HELPERS
# =========================================================
def print_agent_conversation(result: dict):
    print("\nAgent Conversation:\n")

    for msg in result.get("messages", []):
        agent = msg.get("agent", "unknown")
        msg_type = msg.get("type")

        if msg_type == "crawler_result":
            print(f"  {agent.capitalize()}:")
            print(f"   {msg.get('content') or msg.get('note')}\n")

        elif msg_type == "classification_result":
            print(f"  {agent.capitalize()} (LLM Classification):")
            print(f"   Attempt: {msg.get('attempt')}")
            print(f"   Category: {msg.get('category')}")
            print(f"   Category Score: {msg.get('category_score')}")
            print(f"   Authenticity: {msg.get('authenticity_level')} ({msg.get('authenticity_score')})")
            print(f"   Severity: {msg.get('severity_level')} ({msg.get('severity')})")
            print(f"   Reasoning: {msg.get('classifier_reasoning')}\n")

        elif msg_type == "classifier_feedback":
            print(f"  {agent.capitalize()} → Classifier Feedback:")
            print(f"   Attempt: {msg.get('attempt')}")
            print(f"   Instruction: {msg.get('instruction')}")
            print(f"   Reason: {msg.get('reason')}")
            print(f"   Review: {msg.get('review_of_classifier')}\n")

        elif msg_type == "decision_result":
            print(f"  {agent.capitalize()} (Final Review):")
            print(f"   Attempt: {msg.get('attempt')}")
            print(f"   Decision: {msg.get('decision')}")
            print(f"   Instruction: {msg.get('instruction')}")
            print(f"   Reason: {msg.get('decision_reason')}")
            print(f"   Review of Classifier: {msg.get('review_of_classifier')}\n")

        else:
            # Generic fallback for website/debug compatibility.
            content = (
                msg.get("content")
                or msg.get("reasoning")
                or msg.get("llm_reasoning")
                or msg.get("decision_reason")
                or msg.get("note")
                or "No message content."
            )
            print(f"  {agent.capitalize()}:")
            print(f"   {content}\n")

    print("-" * 40)


# =========================================================
# 12. MAIN
# =========================================================
if __name__ == "__main__":
    with open("data/mock_posts.json", "r", encoding="utf-8") as f:
        mock_posts = json.load(f)

    all_results = []

    for i, post in enumerate(mock_posts, start=1):
        post["incident_id"] = i
        final_state = run_pipeline_for_1_post(post)
        all_results.append(final_state)

    print("\n=== INCIDENT RESULTS ===\n")

    accepted = 0
    rejected = 0
    retry_final = 0

    for result in all_results:
        if result["decision"] == "publish":
            accepted += 1
        elif result["decision"] == "reject":
            rejected += 1
        elif result["decision"] == "needs_retry":
            retry_final += 1

        print(f"Incident ID: {result['incident_id']}")
        print(f"Retry Count: {result['retry_count']}")
        print(f"Decision: {result['decision'].upper()}")
        print(f"Decision Reason: {result.get('decision_reason')}")
        print(f"Category: {result.get('category')}")
        print(f"Category Score: {result.get('category_score')}")
        print(f"Authenticity Level: {result.get('authenticity_level')}")
        print(f"Authenticity Score: {result.get('authenticity_score')}")
        print(f"Severity Level: {result.get('severity_level')}")
        print(f"Severity: {result.get('severity')}")
        print(f"Location: {result.get('location_text')}")
        print(f"Action: {result.get('action_text')}")
        print(f"Time: {result.get('normalized_time')}")
        print(f"Cleaned Content: {result.get('cleaned_content')}")

        if result.get("classifier_reasoning"):
            print(f"Classifier Reasoning: {result['classifier_reasoning']}")

        print_agent_conversation(result)

    print("\n=== SUMMARY ===\n")

    total = len(all_results)

    print(f"Total Incidents: {total}")
    print(f"Accepted (Published): {accepted}")
    print(f"Rejected: {rejected}")
    print(f"Still Needs Retry: {retry_final}")

    if total > 0:
        print(f"Acceptance Rate: {round((accepted / total) * 100, 1)}%")
