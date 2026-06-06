import pymysql

try:
    connection = pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="mysql",
        database="gymface",
        port=3306
    )

    print("Database Connected Successfully")

except Exception as e:
    print("Error:", e)