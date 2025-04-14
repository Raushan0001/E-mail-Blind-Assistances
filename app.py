import os
import time
import smtplib
import imaplib
import random
import json
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_pymongo import PyMongo
from dotenv import load_dotenv
from gtts import gTTS
from PIL import Image
import pytesseract

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key')

# MongoDB setup
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/email_system")
mongo = PyMongo(app)

# Directories setup
save_folder = "downloaded_images"
audio_folder = "static/converted_audio"
os.makedirs(save_folder, exist_ok=True)
os.makedirs(audio_folder, exist_ok=True)

# Email settings
EMAIL, PASSWORD = os.getenv('EMAIL'), os.getenv('PASSWORD')
IMAP_SERVER, SMTP_SERVER = 'imap.gmail.com', 'smtp.gmail.com'

# Important keywords for filtering emails
IMPORTANT_KEYWORDS = ["urgent", "important", "meeting", "deadline", "asap", "action required", "priority", "please review"]

# Convert text to speech
def text_to_speech(text, filename, retries=3):
    for attempt in range(retries):
        try:
            tts = gTTS(text)
            tts.save(filename)
            print(f"Audio saved: {filename}")
            return filename  # Ensure the file path is returned
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(random.uniform(2, 5))
    print("Failed to generate speech after multiple attempts.")
    return None

# Connect to Gmail IMAP
def connect_to_email(email, password):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(email, password)
        mail.select("inbox")
        return mail
    except Exception as e:
        print(f"Connection error: {e}")
        return None

# Fetch unseen emails, filter them, and generate audio files
def fetch_and_process_emails():
    if 'email' not in session or 'password' not in session:
        return []

    mail = connect_to_email(session.get('email'), session.get('password'))
    if not mail:
        return []

    emails = []
    status, messages = mail.search(None, "UNSEEN")
    if status != "OK":
        return []

    for num in messages[0].split():
        res, msg_data = mail.fetch(num, "(RFC822)")
        if res != "OK":
            continue

        raw_email = msg_data[0][1]
        email_message = email.message_from_bytes(raw_email)
        subject = ''.join([part.decode(enc if enc else 'utf-8', 'ignore') if isinstance(part, bytes) else part
                           for part, enc in decode_header(email_message.get("Subject", "(No Subject)"))])

        body = ""
        for part in email_message.walk() if email_message.is_multipart() else [email_message]:
            if part.get_content_type() == "text/plain" and "attachment" not in part.get("Content-Disposition", ""):
                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
            elif part.get_content_type().startswith("image/"):
                image_filename = os.path.join(save_folder, f"image_{num.decode()}.png")
                with open(image_filename, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                body += f"\n\nImage Text:\n{pytesseract.image_to_string(Image.open(image_filename))}"

        # Apply keyword filtering
        if any(keyword.lower() in (subject + body).lower() for keyword in IMPORTANT_KEYWORDS):
            full_text = f"Subject: {subject}\n\nBody: {body or '(No Body)'}"
            audio_filename = f"email_{int(time.time())}_{num.decode()}.mp3"
            audio_path = os.path.join(audio_folder, audio_filename)
            text_to_speech(full_text, audio_path)

            emails.append({
                "subject": subject,
                "body": body,
                "audio_file": audio_filename  # Store only the filename, not full path
            })
    
    mail.logout()
    return emails

# Store sent emails in MongoDB
def save_sent_email_to_mongo(to_addresses, subject, body):
    sent_email = {
        "to": to_addresses,
        "subject": subject,
        "body": body,
        "sent_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    mongo.db.sent_emails.insert_one(sent_email)

# Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        session['email'], session['password'] = email, password
        flash('Logged in successfully!', 'success')
        return redirect(url_for('menu'))
    return render_template('login.html')

# ✅ Logout route (fixes the error)
@app.route('/logout')
def logout():
    session.clear()  # Clear session data
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))  # Redirect to login page


@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/inbox')
def inbox():
    return render_template("inbox.html", emails=fetch_and_process_emails())

@app.route('/sent')
def sent():
    sent_emails = mongo.db.sent_emails.find().sort("sent_time", -1)
    return render_template('sent.html', sent_emails=sent_emails)

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if request.method == 'POST':
        to_addresses = request.form.getlist('to')
        subject = request.form.get('subject')
        body = request.form.get('body')

        if not to_addresses or not subject or not body:
            flash('All fields are required.', 'error')
            return render_template('compose.html')

        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = EMAIL, ', '.join(to_addresses), subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            with smtplib.SMTP(SMTP_SERVER, 587) as server:
                server.starttls()
                server.login(EMAIL, PASSWORD)
                server.send_message(msg)
                save_sent_email_to_mongo(to_addresses, subject, body)
                flash('Email sent successfully!', 'success')
                return redirect(url_for('sent'))
        except smtplib.SMTPException as e:
            flash(f'Error sending email: {str(e)}', 'error')
    return render_template('compose.html')

# Serve audio files
@app.route('/play_audio/<filename>')
def play_audio(filename):
    return send_from_directory(audio_folder, filename)

# Download audio files
@app.route('/download_audio/<filename>')
def download_audio(filename):
    return send_from_directory(audio_folder, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
