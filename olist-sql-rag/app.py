import streamlit as st
import pandas as pd
from sql_generator import generate_sql
from database import DatabaseManager
from config import Config

# Page Configuration
st.set_page_config(
    page_title="Olist Data Assistant",
    layout="wide"
)

# Initialize Database
db = DatabaseManager()

# Sidebar - Configuration Status
st.sidebar.title("System Status")
if Config.validate():
    st.sidebar.success("Config: Connected")
else:
    st.sidebar.error("Config: Missing Keys")

# Main UI
st.title("Olist E-Commerce AI Assistant")
st.markdown("Ask any question about orders, products, or customers in plain English.")

# User Input
user_query = st.text_input("Enter your question:", placeholder="e.g., What are the top 5 cities by revenue?")

if user_query:
    with st.spinner("Analyzing data..."):
        # 1. Generate SQL
        ai_response = generate_sql(user_query)

        if "error" in ai_response:
            st.error(f"AI Error: {ai_response['error']}")
        else:
            sql = ai_response["sql"]
            explanation = ai_response["explanation"]

            # 2. Display the AI's reasoning in an expander
            with st.expander("View AI Reasoning & SQL Query"):
                st.write(f"**Explanation:** {explanation}")
                st.code(sql, language="sql")

            # 3. Execute Query
            db_result = db.execute_query(sql)

            if "error" in db_result:
                st.error(f"Database Error: {db_result['error']}")
            else:
                data = db_result["data"]
                count = db_result["count"]

                if count == 0:
                    st.warning("No results found for this query.")
                else:
                    st.subheader(f"Results ({count} rows found)")
                    
                    # 4. Display results as a clean table
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)

                    # 5. Simple Visualization (if the data has numeric values)
                    # Check if there's a numeric column to plot
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if len(numeric_cols) > 0 and len(df) > 1:
                        st.subheader("Visual Analysis")
                        # Use the first text column for X and first numeric for Y
                        text_cols = df.select_dtypes(include=['object']).columns
                        if len(text_cols) > 0:
                            st.bar_chart(data=df, x=text_cols[0], y=numeric_cols[0])

# Footer
st.markdown("---")
st.caption("Powered by Groq Llama-3 and MySQL")