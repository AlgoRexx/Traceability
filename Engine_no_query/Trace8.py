from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import pandas as pd
import sqlite3
import traceback
from os import listdir, path
from os.path import isfile, join, splitext
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime

app = FastAPI()

templates = Jinja2Templates(directory="templates")

fixed_table_name = "csv_data_table"

class DatabaseManager:
    def __init__(self, database_file: str):
        self.conn = sqlite3.connect(database_file)

    def close_connection(self):
        if self.conn:
            self.conn.close()

    def execute_query(self, query: str, params: tuple = ()):
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            self.conn.commit()
            return cursor
        except Exception as e:
            print(f"Error executing query: {str(e)}")
            raise

def startup_event():
    database_file = 'Trace3.db'

    if not path.exists(database_file):
        print(f"Creating SQLite database: {database_file}")
        open(database_file, 'a').close()

    app.db_manager = DatabaseManager(database_file=database_file)

def shutdown_event():
    app.db_manager.close_connection()

app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)

def csv_to_sql(csv_files, database_manager):
    try:
        # Connect to the SQLite database outside the loop
        conn = database_manager.conn

        for csv_file in csv_files:
            print(f"Processing CSV file: {csv_file}")
            df = pd.read_csv(csv_file)
            #print("DataFrame content:")
            #print(df.head())
            df['source_file'] = splitext(csv_file)[0]

            # Append the DataFrame to the existing table
            df.to_sql(fixed_table_name, conn, index=False, if_exists='replace')

            print(f"Data from {csv_file} added to the {fixed_table_name} table")

    except Exception as e:
        print(f"Error in csv_to_sql: {str(e)}")
        traceback.print_exc()
    
def get_row_by_datetime(database_manager, datetime_value):
    try:
        query = f'SELECT * FROM {fixed_table_name} WHERE "Engine no" = ?;'
        cursor = database_manager.execute_query(query, params=(datetime_value,))
        df_row = pd.DataFrame(cursor.fetchall(), columns=[desc[0] for desc in cursor.description])
        return df_row

    except Exception as e:
        print(f"Error in get_row_by_datetime: {str(e)}")
        return pd.DataFrame()

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})

@app.post("/result/")
async def read_item(request: Request, barcode: str = Form(...)):
    current_folder = '/Users/anand/Desktop/ai/grad/Engine_no_query'
    csv_files = [join(current_folder, f) for f in listdir(current_folder) if
                 isfile(join(current_folder, f)) and f.endswith('.csv')]

    if not csv_files:
        return {"error": "No CSV files found in the specified folder."}

    try:
        csv_to_sql(csv_files, app.db_manager)

        df_row = get_row_by_datetime(app.db_manager, barcode)

        if not df_row.empty:
            df_row_html = df_row.to_html(index=False, escape=False, classes="styled-table")
            df_row_html = df_row_html.replace('<td>OK</td>', '<td style="background-color: green;">OK</td>')
            df_row_html = df_row_html.replace('<td>None</td>', '<td style="background-color: yellow;">None</td>')
            df_row_html = df_row_html.replace('<td>BB</td>', '<td style="background-color: red;">BB</td>')

            result_data = df_row_html
            df_row['Reception date/time'] = pd.to_datetime(df_row['Reception date/time'], format='%M:%S.%f')

            # Plotting
            plt.plot(df_row['Reception date/time'], df_row['Torque'])  # Replace 'SomeColumn' with the column you want to plot
            plt.title('Your Plot Title')
            plt.xlabel('Date & Time')
            plt.ylabel('Torque')

            # Save the plot to a BytesIO object
            plot_bytes = BytesIO()
            plt.savefig(plot_bytes, format='png')
            plt.close()

            # Embed the plot in the HTML response
            plot_data = base64.b64encode(plot_bytes.getvalue()).decode('utf-8')
            graph_data = f'<img src="data:image/png;base64,{plot_data}">'

        else:
            result_data = f"No row found for Engine no. {barcode} or table is empty."
            graph_data = f"Not found."

    except Exception as e:
        result_data = f"Error: {str(e)}"
        graph_data = ""

    return templates.TemplateResponse("result.html", {"request": request, "result_data": result_data, "graph_data": graph_data})
