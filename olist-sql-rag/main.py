import pandas as pd
from sql_generator import generate_sql
from database import DatabaseManager
from config import Config

def main():
    # 1. Validate configuration
    if not Config.validate():
        return

    # 2. Initialize database
    db = DatabaseManager()

    print("-" * 50)
    print("OLIST DATABASE ASSISTANT")
    print("Type 'exit' or 'quit' to stop.")
    print("-" * 50)

    while True:
        # 3. Get user input
        user_input = input("\nAsk a question: ").strip()

        if user_input.lower() in ['exit', 'quit']:
            print("Closing assistant.")
            break

        if not user_input:
            continue

        print("Analyzing...")

        # 4. Generate SQL from AI
        ai_response = generate_sql(user_input)

        if "error" in ai_response:
            print(f"AI Error: {ai_response['error']}")
            continue

        sql = ai_response["sql"]
        explanation = ai_response["explanation"]

        print(f"Reasoning: {explanation}")
        print(f"Running SQL: {sql}")

        # 5. Execute on Database
        db_result = db.execute_query(sql)

        if "error" in db_result:
            print(f"Database Error: {db_result['error']}")
            continue

        # 6. Display Results
        data = db_result["data"]
        count = db_result["count"]

        if count == 0:
            print("No results found for this query.")
        else:
            print(f"Found {count} results:")
            # Use Pandas to display the result as a clean table
            df = pd.DataFrame(data)
            print("-" * 50)
            print(df.to_string(index=False))
            print("-" * 50)

if __name__ == "__main__":
    main()