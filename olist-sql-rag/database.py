import mysql.connector
from config import Config

class DatabaseManager:
    def __init__(self):
        self.conn_params = {
            'host': Config.DB_HOST,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'database': Config.DB_NAME
        }

    def execute_query(self, sql):
        """Safe execution of SELECT queries only"""
        sql_upper = sql.upper().strip()
        
        # Security Check: Only allow SELECT
        if not sql_upper.startswith("SELECT"):
            return {"error": "Security Block: Only SELECT queries are allowed."}
        
        # Security Check: Block dangerous words
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE"]
        if any(word in sql_upper for word in forbidden):
            return {"error": "Security Block: Dangerous keyword detected."}

        try:
            conn = mysql.connector.connect(**self.conn_params)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            return {"data": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e)}

if __name__ == "__main__":
    db = DatabaseManager()
    #Sample test query
    print("Testing database connection...")
    result = db.execute_query("SELECT * FROM users LIMIT 1")
    print(result)