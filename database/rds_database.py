import pymysql
from dotenv import load_dotenv
import os



load_dotenv()
HOST = os.getenv("RDS_HOST")
PORT = os.getenv("RDS_PORT")
USER = os.getenv("RDS_USER")  
PASSWORD = os.getenv("RDS_PASSWORD")  
# DB_NAME = os.getenv("RDS_DB_NAME")  

class rds_database:
    def __init__(self, db_name):
        self.conn = pymysql.connect(host=HOST, user=USER, passwd=PASSWORD, db=db_name, port=3306)
        print("Connection established successfully!")
        self.cursor = self.conn.cursor()
        
    # Example usage:
    # self.bulk_insert_data([{'username': 'alice', 'age': 30}, {'username': 'bob', 'age': 25}])
    def bulk_insert_data(self,table_name, records):
        if not records:
            return "No records to insert."

        # Extracting column names from the first dictionary (assuming all records are uniform)
        columns = ', '.join(records[0].keys())
        placeholders = ', '.join(['%s'] * len(records[0]))

        # Construct the SQL statement
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        # Preparing the values to insert
        values = [tuple(record.values()) for record in records]

        # Assuming cursor is a cursor object connected to your database
        # with connection being a database connection
        try:
            cursor = self.cursor
            cursor.executemany(sql, values)
            self.conn.commit()
            cursor.close()
            print(f"Successfully inserted {len(records)} records into {table_name}.")
            return "Success"
        except Exception as e:
            print(f"Error inserting records: {e}")
            return str(e)
        

    # Example usage:
    # self.update_data('users', {'age': 31}, {'username': 'alice'})
    def update_data(self, table_name ,set_values, conditions):
    # Preparing SET part of SQL command
        set_clause = ', '.join([f"{key} = %s" for key in set_values.keys()])
        set_values_list = list(set_values.values())

        # Preparing WHERE part of SQL command
        condition_clause = ' AND '.join([f"{key} = %s" for key in conditions.keys()])
        condition_values_list = list(conditions.values())

        # Complete values list for SQL execution
        values = set_values_list + condition_values_list

        # Constructing the SQL statement
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {condition_clause}"

        # Executing the update
        try:
            cursor = self.cursor
            cursor.execute(sql, values)
            self.conn.commit()
            cursor.close()
            print(f"Successfully updated records in {table_name}.")
            return "Success"
        except Exception as e:
            print(f"Error updating records: {e}")
            return str(e)

    # Example usage:
    # query results for all users with username 'alice' specifying desired columns
    # results = self.query_data('users', columns=['username', 'age'], conditions={'username': 'alice'})
    # print(results)

    # query all data from a table without conditions
    # all_users = self.query_data('users')
    # print(all_users)
    def query_data(self,table_name,columns=None, conditions=None):
        # Default to selecting all columns if none are specified
        columns_clause = ', '.join(columns) if columns else '*'

        # Constructing the WHERE clause if conditions are provided
        if conditions:
            condition_clauses = ' AND '.join([f"{key} = %s" for key in conditions.keys()])
            condition_values = list(conditions.values())
            sql = f"SELECT {columns_clause} FROM {table_name} WHERE {condition_clauses}"
        else:
            sql = f"SELECT {columns_clause} FROM {table_name}"

        # Executing the query
        try:
            cursor = self.conn.cursor()
            if conditions:
                cursor.execute(sql, condition_values)
            else:
                cursor.execute(sql)

            # Fetching all the records
            records = cursor.fetchall()
            cursor.close()

            # Optionally, return records as a list of dictionaries for better readability
            if records:
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, record)) for record in records]
            return []
        except Exception as e:
            print(f"Error querying data: {e}")
            return []

