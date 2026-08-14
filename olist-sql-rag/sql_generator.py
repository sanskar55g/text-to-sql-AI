import json
from groq import Groq  
from config import Config

# Initialize Groq Client
client = Groq(api_key=Config.GROQ_API_KEY)

try:
    with open("rag_context.md", "r") as f:
        RAG_CONTEXT = f.read()
except FileNotFoundError:
    print(" Error: rag_context.md not found!")
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

## OUTPUT FORMAT
You must return your response in JSON format with two keys:
1. "sql": The generated MySQL query.
2. "explanation": A short description of the query.
"""

def generate_sql(user_question):
    try:
        response = client.chat.completions.create(
            # Using Llama 3 70B on Groq - it's excellent for SQL
            model="llama-3.3-70b-versatile", 
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_question}
            ],
            # Tell Groq we want JSON
            response_format={"type": "json_object"},
            temperature=0 
        )
        
        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    test_questions = [
        "How many customers are in Sao Paulo?",
        "What is our total revenue?",
        "Show me the top 5 product categories by number of orders."
    ]
    
    print("\n--- Testing Groq SQL Generation ---")
    for q in test_questions:
        print(f"\nQuestion: {q}")
        res = generate_sql(q)
        if "error" in res:
            print(f"Error: {res['error']}")
        else:
            print(f"Generated SQL: {res['sql']}")
            print(f"Explanation: {res['explanation']}")