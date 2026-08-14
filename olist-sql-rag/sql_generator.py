import json
from groq import Groq
from config import Config

# Initialize Groq Client
client = Groq(api_key=Config.GROQ_API_KEY)

try:
    with open("rag_context.md", "r") as f:
        RAG_CONTEXT = f.read()
except FileNotFoundError:
    print("Error: rag_context.md not found!")
    exit()

SYSTEM_PROMPT = f"""You are a SQL expert for the Olist E-commerce database.
Your job is to convert natural language questions into accurate MySQL SELECT queries.

{RAG_CONTEXT}

## CONSTRAINTS
- Use ONLY 'SELECT' statements.
- Always use the table aliases: u (users), o (orders), oi (order_items), p (products).
- For 'revenue', use: SUM(oi.price + oi.freight_value).
- For 'customers', use customer_unique_id to count unique people.
- Always add a LIMIT 100 to your queries.
- NEVER invent a column, table, or metric that is not explicitly defined in the schema/context above.

## AMBIGUITY RULE (STRICT)
If a question contains ANY word or phrase whose meaning is not fixed by the schema/context —
including but not limited to: "best", "worst", "top", "active", "inactive", "high value",
"loyal", "underperforming", "popular", "slow", "fast", "good", "bad", "cheap", "expensive" —
you MUST ask for clarification using clarification_type "options".

If a question implies a time range but does not state one — e.g. "recent orders", "this year",
"lately", "last quarter's revenue", "orders in [some period]" without exact dates —
you MUST ask for clarification using clarification_type "date_range".

Also ask for clarification if a ranking/limit is implied but not stated ("show me some", "a few"),
or the question could refer to more than one entity/metric.

Only skip clarification when the question is fully self-contained: every metric, filter, and
scope is either explicitly stated or has exactly one definition per the CONSTRAINTS/context above.

## CONVERSATION CONTEXT RULE (VERY IMPORTANT)
You may receive prior turns in this conversation. If an earlier assistant turn asked a
clarification question, and the latest user message answers it (contains "Start date" and
"End date", or picks one of the previously offered options, or begins with "Chosen interpretation:"
or "Date range answer:"), you MUST:
- Look back at the ORIGINAL question from earlier in the conversation.
- Combine it with the new answer.
- Produce a final "sql" response immediately. Do NOT ask for clarification again about
  something that has already been answered in this conversation.
- Use supplied dates as literal string bounds, e.g.
  o.order_purchase_timestamp BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'.
- If the answer resolves ambiguity but a second, DIFFERENT ambiguity remains (e.g. user
  clarified "recent" with dates but "best" is still undefined), you may ask ONE more
  clarification for that remaining ambiguity only — never repeat a question already answered.

## OUTPUT FORMAT
Return JSON with ONE of these shapes:

Shape A — the question is fully unambiguous, or a prior clarification has just been resolved:
{{
  "type": "sql",
  "sql": "<the MySQL query>",
  "explanation": "<short description of what it does>"
}}

Shape B — ambiguous metric/entity/ranking, offer discrete choices:
{{
  "type": "clarification",
  "clarification_type": "options",
  "question": "<a specific clarifying question>",
  "options": ["<option 1>", "<option 2>", "..."]
}}

Shape C — ambiguous or missing time range, ask for a date range specifically:
{{
  "type": "clarification",
  "clarification_type": "date_range",
  "question": "<a specific clarifying question about the date range>"
}}

Never mix shapes. Never guess a definition or a date range just to avoid asking.
When in doubt, ask — a clarification is always preferred over a guess.
Respond with JSON only. No preamble, no markdown fences.

## FEW-SHOT EXAMPLES

Q: "Who is our best customer?"
A: {{"type": "clarification", "clarification_type": "options",
     "question": "By what measure do you want to rank customers?",
     "options": ["Highest total purchase amount", "Most orders placed", "Earliest first order (loyalty)"]}}

Q: "Show me our recent orders."
A: {{"type": "clarification", "clarification_type": "date_range",
     "question": "What date range should I use for 'recent orders'?"}}

Q: "What was our revenue last quarter?"
A: {{"type": "clarification", "clarification_type": "date_range",
     "question": "Please specify the exact start and end date for the quarter you mean."}}

Q: "What is our total revenue?"
A: {{"type": "sql", "sql": "SELECT SUM(oi.price + oi.freight_value) AS total_revenue FROM order_items oi LIMIT 100;",
     "explanation": "Sums price + freight_value across all order items, per the revenue definition."}}

Q: "How many customers are in Sao Paulo?"
A: {{"type": "sql", "sql": "SELECT COUNT(DISTINCT u.customer_unique_id) AS customer_count FROM users u WHERE u.customer_city = 'sao paulo' LIMIT 100;",
     "explanation": "Counts unique customers whose city is Sao Paulo — fully specified, no ambiguity."}}

## Example of a resolved follow-up (context rule in action)

Turn 1 - User: "Show me our recent orders."
Turn 1 - Assistant: {{"type": "clarification", "clarification_type": "date_range",
     "question": "What date range should I use for 'recent orders'?"}}
Turn 2 - User: "Date range answer: Start date: 2024-01-01, End date: 2024-03-31"
Turn 2 - Assistant: {{"type": "sql",
     "sql": "SELECT o.order_id, o.order_purchase_timestamp FROM orders o WHERE o.order_purchase_timestamp BETWEEN '2024-01-01' AND '2024-03-31' LIMIT 100;",
     "explanation": "Lists orders placed between the specified start and end dates, resolving the earlier 'recent orders' question."}}
"""

VALID_TYPES = {"sql", "clarification", "error"}
VALID_CLARIFICATION_TYPES = {"options", "date_range"}


def _validate_response(result):
    """
    Defensive check on the model's JSON so the frontend never has to guess
    about missing keys. Returns (is_valid, normalized_result).
    """
    if not isinstance(result, dict) or "type" not in result:
        return False, {"type": "error", "error": "Malformed AI response: missing 'type' field."}

    if result["type"] == "sql":
        if "sql" not in result:
            return False, {"type": "error", "error": "Malformed AI response: 'sql' response missing 'sql' key."}
        result.setdefault("explanation", "")
        return True, result

    if result["type"] == "clarification":
        if result.get("clarification_type") not in VALID_CLARIFICATION_TYPES:
            return False, {"type": "error", "error": "Malformed AI response: invalid or missing 'clarification_type'."}
        if "question" not in result:
            return False, {"type": "error", "error": "Malformed AI response: clarification missing 'question'."}
        if result["clarification_type"] == "options":
            result.setdefault("options", [])
        return True, result

    if result["type"] == "error":
        return True, result

    return False, {"type": "error", "error": f"Malformed AI response: unknown type '{result['type']}'."}


def generate_sql(user_question, history=None, max_retries=1):
    """
    user_question: the latest user message — either a fresh question, or an answer to a
                    previous clarification (e.g. "Date range answer: Start date: 2024-01-01,
                    End date: 2024-03-31", or "Chosen interpretation: Most orders placed").
    history: list of prior turns as {"role": "user"/"assistant", "content": "..."} dicts,
             in chronological order. Assistant turns should contain the raw JSON string
             previously returned, so the model can see its own prior question and resolve it.
    max_retries: how many times to retry once on a JSON parse failure (Groq occasionally
                 returns malformed JSON under load).
    """
    history = history or []
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_question}]
    )

    attempts = 0
    last_error = None

    while attempts <= max_retries:
        attempts += 1
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw = response.choices[0].message.content
            result = json.loads(raw)

            is_valid, normalized = _validate_response(result)
            if is_valid:
                return normalized
            last_error = normalized.get("error", "Invalid response shape.")
            # Nudge the model on retry to strictly follow the schema
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": "Your last response did not match the required JSON schema. "
                           "Respond again with valid JSON matching Shape A, B, or C exactly.",
            })

        except json.JSONDecodeError as e:
            last_error = f"Could not parse AI response as JSON: {e}"
        except Exception as e:
            return {"type": "error", "error": str(e)}

    return {"type": "error", "error": last_error or "Unknown error generating SQL."}


if __name__ == "__main__":
    print("\n--- Testing Groq SQL Generation (with context) ---")

    q1 = "Show me our recent orders."
    res1 = generate_sql(q1)
    print(f"\nQ1: {q1}")
    print(json.dumps(res1, indent=2))

    history = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": json.dumps(res1)},
    ]
    q2 = "Date range answer: Start date: 2024-01-01, End date: 2024-03-31"
    res2 = generate_sql(q2, history=history)
    print(f"\nQ2: {q2}")
    print(json.dumps(res2, indent=2))