from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from routes.batch_routes import batch_routes
from routes.patient_routes import patient_bp
from routes.json_process_routes import json_process_bp
import pandas as pd
import gridfs
import io
from pymongo import MongoClient
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders




# Define the trusted domain
ALLOWED_ORIGINS = ["https://website-backend-6w0g.onrender.com"]

# Configure CORS to allow only the trusted domain
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

# ✅ Register Blueprints
app.register_blueprint(batch_routes)
app.register_blueprint(patient_bp)
app.register_blueprint(json_process_bp)



# ✅ Connect to MongoDB
client = MongoClient("mongodb+srv://pavanshankar9000:pavan%409000@project1.gfku5.mongodb.net/?retryWrites=true&w=majority")
db = client["Finish_db"]
fs = gridfs.GridFS(db)
submitted_reports_collection = db["submitted_reports"]
availability_collection = db["availability_status"]  # ✅ New collection for availability status


# ✅ Email Credentials (Use App Password for Gmail)
SENDER_EMAIL = "chanduchandu913303@gmail.com"#personal testing  email
SENDER_PASSWORD = "xwcq vlpd kjeg ewcs"  # App Password for Gmail


SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
RECIPIENT_EMAIL = "pavanshankar9000@gmail.com"  # Change this to your required email


@app.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    """
    Uploads PDF files for a patient inside a batch and stores them in MongoDB GridFS.
    """
    try:
        batch_name = request.args.get("batch_name", "").strip()
        patient_id = request.args.get("patient_id", "").strip()

        if "pdfs" not in request.files:
            return jsonify({"error": "No PDF file uploaded"}), 400

        uploaded_files = request.files.getlist("pdfs")  # Multiple PDFs

        file_ids = []
        for file in uploaded_files:
            file_id = fs.put(file, filename=file.filename, patient_id=patient_id, batch=batch_name)
            file_ids.append(str(file_id))

        return jsonify({"message": "PDFs uploaded successfully", "file_ids": file_ids}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to upload PDFs: {str(e)}"}), 500


@app.route("/excel-download", methods=["POST"])
def generate_excel():
    """
    Receives JSON data, stores it in MongoDB, and sends the Excel report via email.
    """
    try:
        json_data = request.get_json()
        selected_patient = json_data.get("selectedPatient", "").strip()
        selected_batch = json_data.get("selectedBatch", "").strip()
        headers = json_data.get("headers", [])
        report_data = json_data.get("data", [])  # Extract the report data

        if not selected_patient or not selected_batch or not report_data:
            return jsonify({"error": "Missing required fields or empty data"}), 400

        # ✅ Store JSON data in MongoDB
        report_entry = {
            "batch": selected_batch,
            "patient_id": selected_patient,
            "report_data": report_data,
            "timestamp": datetime.utcnow()
        }
        inserted_id = submitted_reports_collection.insert_one(report_entry).inserted_id

        # ✅ Generate Excel file and get file path
        filename = f"{selected_patient}_Scoring_chart.xlsx"
        file_path = convert_json_to_excel(report_data, headers, filename)
        if not file_path:
            return jsonify({"error": "Failed to generate Excel file"}), 500

        # ✅ Send Email with the generated file
        recipient_emails = ["pavanshankar9000@gmail.com", "bunnybunny913303@gmail.com", "bunnbunn913303@gmail.com"]
        email_sent = send_email_with_attachment(recipient_emails, file_path, filename,selected_patient)

        # ✅ Delete the file after sending the email
        os.remove(file_path)

        if email_sent:
            return jsonify({
                "message": "Report submitted and emailed successfully",
                "document_id": str(inserted_id)
            }), 200
        else:
            return jsonify({"error": "Failed to send email, but data is stored"}), 500

    except Exception as e:
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500




# @app.route("/f/<batch_name>/<patient_id>", methods=["GET"])
# def download_excel(batch_name, patient_id):
#     """
#     Fetches the latest Excel file for a patient from MongoDB GridFS.
#     """
#     try:
#         file_doc = db.fs.files.find_one({"patient_id": patient_id, "batch": batch_name}, sort=[("uploadDate", -1)])
#         if not file_doc:
#             return jsonify({"error": "No Excel file found for this patient"}), 404

#         file_id = file_doc["_id"]
#         file_data = fs.get(file_id)

#         return send_file(
#             io.BytesIO(file_data.read()),
#             as_attachment=True,
#             download_name=file_doc["filename"],
#             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#         )

#     except Exception as e:
#         return jsonify({"error": f"Error fetching Excel file: {str(e)}"}), 500

@app.route("/update-availability", methods=["POST"])
def update_availability():
    """
    Updates patient availability status (Available = 🟠, Not Available = 🔴).
    """
    try:
        json_data = request.get_json()
        batch_name = json_data.get("batch_name", "").strip()
        patient_id = json_data.get("patient_id", "").strip()
        availability = json_data.get("availability", "").strip()

        if not batch_name or not patient_id or availability not in ["available", "not_available"]:
            return jsonify({"error": "Invalid data received"}), 400

        availability_collection.update_one(
            {"batch": batch_name, "patient_id": patient_id},
            {"$set": {"available": availability == "available"}},
            upsert=True
        )

        return jsonify({"message": "Availability status updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to update availability: {str(e)}"}), 500

@app.route("/get-report-status", methods=["GET"])
def get_report_status():
    """
    Fetches report submission and availability status from MongoDB.
    """
    batch_name = request.args.get("batch_name", "").strip()
    if not batch_name:
        return jsonify({"error": "Batch name is required"}), 400

    patient_reports = {}
    reports = submitted_reports_collection.find({"batch": batch_name})

    for report in reports:
        patient_id = report["patient_id"]
        patient_reports[patient_id] = {"submitted": True}

    availability_data = availability_collection.find({"batch": batch_name})
    for entry in availability_data:
        patient_id = entry["patient_id"]
        patient_reports.setdefault(patient_id, {})["available"] = entry["available"]

  
    return jsonify(patient_reports), 200
import os

def convert_json_to_excel(data, headers, filename):
    """
    Converts JSON data into an Excel file and saves it on disk instead of using in-memory buffer.
    """
    try:
        if not data:
            df = pd.DataFrame([{"No Data": "N/A"}])
        else:
            df = pd.DataFrame(data)

        # ✅ Normalize column names
        df.columns = df.columns.str.strip().str.lower()
        headers_normalized = [col.strip().lower() for col in headers]

        # ✅ Create a mapping of old column names to expected headers
        column_mapping = {df_col: headers[i] for i, df_col in enumerate(df.columns) if i < len(headers)}

        # ✅ Rename DataFrame columns to match headers
        df.rename(columns=column_mapping, inplace=True)

        # ✅ Ensure all expected headers exist in DataFrame
        for col in headers:
            if col not in df.columns:
                df[col] = ""

        # ✅ Reorder columns based on headers
        df = df[headers]

        # ✅ Define a temporary file path (use `/tmp/` on Render)
        temp_dir = "/tmp"  # Render allows saving files here
        os.makedirs(temp_dir, exist_ok=True)  # Ensure the directory exists
        file_path = os.path.join(temp_dir, filename)

        # ✅ Save DataFrame to an actual Excel file on disk
        with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Report")

        print(f"✅ Excel file saved at: {file_path}")
        return file_path  # Return file path instead of in-memory buffer

    except Exception as e:
        print(f"❌ Error generating Excel file: {str(e)}")
        return None


def send_email_with_attachment(to_emails, file_path, filename,patient_id):
    """
    Sends an email with the generated Excel file as an attachment.
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = ", ".join(to_emails)  # Convert list of emails to a comma-separated string
        msg["Subject"] = f"{patient_id} Scoring Chart"  # ✅ Include patient_id in subject

        body = "Please find the attached Excel file containing the patient report."
        msg.attach(MIMEText(body, "plain"))

        # ✅ Attach the actual file
        with open(file_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())

        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)

        # ✅ Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_emails, msg.as_string())
        server.quit()

        print(f"✅ Email sent with attachment: {filename}")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


