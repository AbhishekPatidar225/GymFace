from fastapi import FastAPI, Depends
from pydantic import BaseModel
import pymysql
from typing import Optional

app = FastAPI()

class Member(BaseModel):
    full_name: str
    phone: str
    membership_plan: str

class UpdateMember(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    membership_plan: Optional[str] = None

# --- 1. The Professional Database Manager (Dependency) ---
def get_db():
    # Step A: Open the connection
    connection = pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="mysql", 
        database="gymface",
        port=3306,
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        # Step B: "yield" pauses this function and hands the connection to your API to use
        yield connection 
    finally:
        # Step C: "finally" guarantees that NO MATTER WHAT (even if the API crashes),
        # the connection is safely closed and returned to the system.
        connection.close()

# --- 2. Endpoints ---

@app.get("/")
def home():
    return {"message": "GymFace Backend Running"}

# Look at the new (db = Depends(get_db)) inside the parentheses!
@app.post("/members")
def add_member(member: Member, db = Depends(get_db)): 
    try:
        # We don't have to connect or disconnect anymore! We just use 'db'.
        cursor = db.cursor()
        sql_query = """
            INSERT INTO member (full_name, phone, membership_plan)
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql_query, (member.full_name, member.phone, member.membership_plan))
        db.commit()
        
        return {"message": f"{member.full_name} successfully added to the database!"}

    except Exception as e:
        return {"error": str(e)}

# Look at the new (db = Depends(get_db)) here too!
@app.get("/members")
def get_members(db = Depends(get_db)):
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM member")
        all_members = cursor.fetchall() 
        return {"members": all_members}

    except Exception as e:
        return {"error": str(e)}

@app.delete("/members/{member_id}")
def delete_member(member_id: int, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        
        # 1. CHECK FIRST: Look for the member to see if they exist
        check_query = "SELECT * FROM member WHERE member_id = %s"
        cursor.execute(check_query, (member_id,))
        existing_member = cursor.fetchone()
        
        # If the query returns nothing, tell the user they can't delete a ghost profile
        if not existing_member:
            return {"error": f"Member with ID {member_id} does not exist."}
            
        # 2. DELETE: If they do exist, execute the delete command
        delete_query = "DELETE FROM member WHERE member_id = %s"
        cursor.execute(delete_query, (member_id,))
        
        # Save the changes permanently
        db.commit()
        
        return {"message": f"Member with ID {member_id} has been successfully deleted."}
        
    except Exception as e:
        return {"error": str(e)}

@app.patch("/members/{member_id}")
def update_member_partial(member_id: int, updated_data: UpdateMember, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        
        # 1. Fetch the current member from the database
        cursor.execute("SELECT * FROM member WHERE member_id = %s", (member_id,))
        existing_member = cursor.fetchone()
        
        if not existing_member:
            return {"error": f"Member with ID {member_id} does not exist. Cannot update."}
            
        # 2. The Logic: If the user sent a new value, use it. Otherwise, keep the old value.
        new_name = updated_data.full_name if updated_data.full_name is not None else existing_member['full_name']
        new_phone = updated_data.phone if updated_data.phone is not None else existing_member['phone']
        new_plan = updated_data.membership_plan if updated_data.membership_plan is not None else existing_member['membership_plan']
        
        # 3. Save the merged data back into the database
        sql_query = """
            UPDATE member 
            SET full_name = %s, phone = %s, membership_plan = %s 
            WHERE member_id = %s
        """
        cursor.execute(sql_query, (new_name, new_phone, new_plan, member_id))
        db.commit()
        
        return {
            "message": f"Member ID {member_id} has been successfully updated!",
            "updated_details": {
                "name": new_name,
                "phone": new_phone,
                "plan": new_plan
            }
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/members/search")
def search_members(query: str, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        
        # We use the SQL 'LIKE' operator to search for partial matches (e.g., typing "Abhi" finds "Abhishek")
        # We search across ID, Name, and Phone all at once!
        sql = """
            SELECT * FROM member 
            WHERE full_name LIKE %s 
            OR phone LIKE %s 
            OR member_id = %s
        """
        
        # Add % around the query so it searches anywhere inside the text
        search_term = f"%{query}%"
        
        # If the user typed a number, we can search the ID column. If not, default to 0.
        search_id = int(query) if query.isdigit() else 0
        
        cursor.execute(sql, (search_term, search_term, search_id))
        results = cursor.fetchall()
        
        if not results:
            return {"message": "No members found matching that search."}
            
        return {"results": results}

    except Exception as e:
        return {"error": str(e)}