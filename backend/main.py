from fastapi import FastAPI, Depends , UploadFile, File, HTTPException
from pydantic import BaseModel
import pymysql
from typing import Optional
import json
import face_recognition
import io
import numpy as np

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
        import pymysql # Ensure this is imported at the top of your file
        # Using DictCursor makes the database return clean JSON dictionaries
        cursor = db.cursor(pymysql.cursors.DictCursor) 
        
        # SCENARIO 1: The user typed only numbers
        if query.isdigit():
            
            # Step A: Check for an EXACT match on member_id first
            cursor.execute("SELECT * FROM member WHERE member_id = %s", (int(query),))
            id_match = cursor.fetchall()
            
            if id_match:
                return {"results": id_match}  # If ID 3 exists, return ONLY member 3.
            
            # Step B: If no member has that exact ID, search phone numbers
            cursor.execute("SELECT * FROM member WHERE phone LIKE %s", (f"%{query}%",))
            results = cursor.fetchall()
            
            if not results:
                return {"message": "No members found matching that search."}
            return {"results": results}
            
        # SCENARIO 2: The user typed letters (must be a name search)
        else:
            cursor.execute("SELECT * FROM member WHERE full_name LIKE %s", (f"%{query}%",))
            results = cursor.fetchall()
            
            if not results:
                return {"message": "No members found matching that search."}
            return {"results": results}
            
    except Exception as e:
        return {"error": str(e)}

@app.post("/members/{member_id}/register-face")
async def register_face(member_id: int, file: UploadFile = File(...), db = Depends(get_db)):
    try:
        cursor = db.cursor()
        
        # 1. CHECK FIRST: Make sure the member actually exists before processing AI data
        cursor.execute("SELECT * FROM member WHERE member_id = %s", (member_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Member ID {member_id} does not exist.")

        # 2. READ IMAGE: Convert the uploaded file into a format the AI can read
        contents = await file.read()
        image = face_recognition.load_image_file(io.BytesIO(contents))
        
        # 3. SCAN FACE: Ask dlib to find faces and extract the 128-point math encodings
        face_encodings = face_recognition.face_encodings(image)
        
        # 4. VALIDATE: Ensure exactly ONE face is in the photo
        if len(face_encodings) == 0:
            return {"error": "No face detected in the image. Please upload a clearer photo."}
        elif len(face_encodings) > 1:
            return {"error": "Multiple faces detected. Please upload a photo of just one person."}
            
        # 5. CONVERT: Take the numpy array and turn it into a standard JSON string
        encoding_list = face_encodings[0].tolist()
        encoding_json = json.dumps(encoding_list)
        
        # 6. SAVE: Update the member's profile in MySQL
        sql_query = """
            UPDATE member 
            SET face_encoding = %s, face_registered = 1 
            WHERE member_id = %s
        """
        cursor.execute(sql_query, (encoding_json, member_id))
        db.commit()
        
        return {"message": f"Face successfully registered for member ID {member_id}!"}
        
    except Exception as e:
        return {"error": str(e)}  



@app.post("/attendance/check-in")
async def check_in(file: UploadFile = File(...), db = Depends(get_db)):
    try:
        # We use DictCursor so we can easily reference column names like 'member_id'
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # 1. READ INCOMING IMAGE: Convert the uploaded file for the AI
        contents = await file.read()
        unknown_image = face_recognition.load_image_file(io.BytesIO(contents))
        
        # 2. SCAN FACE: Extract the 128-point math encoding from the incoming photo
        unknown_encodings = face_recognition.face_encodings(unknown_image)
        
        # Validation: Make sure someone is actually in the photo
        if len(unknown_encodings) == 0:
            return {"error": "No face detected. Please stand closer to the camera."}
        elif len(unknown_encodings) > 1:
            return {"error": "Multiple faces detected. One person at a time, please."}
            
        unknown_encoding = unknown_encodings[0]
        
        # 3. FETCH REGISTERED FACES: Pull everyone from the database who has a face registered
        cursor.execute("SELECT member_id, full_name, face_encoding FROM member WHERE face_registered = 1")
        registered_members = cursor.fetchall()
        
        if not registered_members:
            return {"error": "There are no registered faces in the database to compare against."}
            
        # 4. PREPARE THE DATA: Convert the database JSON strings back into math arrays
        known_encodings = []
        known_member_ids = []
        known_names = []
        
        for member in registered_members:
            # json.loads turns the string back into a Python list
            # np.array turns that list into a math array the AI can use
            encoding_array = np.array(json.loads(member['face_encoding']))
            known_encodings.append(encoding_array)
            known_member_ids.append(member['member_id'])
            known_names.append(member['full_name'])
            
        # 5. THE AI COMPARISON: Compare the unknown face against all known faces
        # This returns a list of True/False values (e.g., [False, True, False])
        matches = face_recognition.compare_faces(known_encodings, unknown_encoding)
        
        # 6. LOG ATTENDANCE IF MATCH FOUND
        if True in matches:
            # Find exactly which person matched
            match_index = matches.index(True)
            matched_member_id = known_member_ids[match_index]
            matched_name = known_names[match_index]
            
            # Log it in the new attendance table
            cursor.execute("INSERT INTO attendance (member_id) VALUES (%s)", (matched_member_id,))
            db.commit()
            
            return {
                "status": "success",
                "message": f"Access Granted! Welcome to the gym, {matched_name}.",
                "member_id": matched_member_id
            }
        else:
            # If the AI loops through everyone and finds no match
            return {
                "status": "denied",
                "error": "Face not recognized. Please see the front desk."
            }
            
    except Exception as e:
        return {"error": str(e)}