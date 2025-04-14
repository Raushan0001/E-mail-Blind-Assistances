import os
import time
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from gtts import gTTS
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from PIL import Image
import pytesseract
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key')

# Directories and setup
save_folder = "downloaded_images"
audio_folder = "static/converted_audio"
os.makedirs(save_folder, exist_ok=True)
os.makedirs(audio_folder, exist_ok=True)

# Path to Tesseract (Windows only)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Email credentials and connection details
EMAIL = os.getenv('EMAIL', 'your_email@example.com')
PASSWORD = os.getenv('PASSWORD', 'your_password')
IMAP_SERVER = 'imap.gmail.com'
SMTP_SERVER = 'smtp.gmail.com'

IMPORTANT_KEYWORDS = {"urgent", "meeting", "update", "action required", "invoice", "payment"}

# Store sent emails in a list (you can use a database for production)
sent_emails = []

# Convert text to speech and save audio file
def text_to_speech(text, filename):
    gTTS(text).save(filename)

# Connect to the email server
def connect_to_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")
        return mail
    except Exception as e:
        print(f"Error connecting to email: {e}")
        return None

# Fetch unread emails and create audio files for each
def fetch_and_convert_emails():
    mail = connect_to_email()
    if not mail:
        return []

    emails = []
    _, search_data = mail.search(None, "UNSEEN")
    for num in search_data[0].split():
        _, data = mail.fetch(num, "(RFC822)")
        email_message = email.message_from_bytes(data[0][1])

        # Decode subject
        subject, encoding = decode_header(email_message.get("Subject"))[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        elif subject is None:
            subject = "(No Subject)"
        
        # Extract body
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" and part.get("Content-Disposition") is None:
                    part_payload = part.get_payload(decode=True)
                    if part_payload:
                        body += part_payload.decode("utf-8", errors="ignore")
                elif content_type.startswith("image/"):
                    image_data = part.get_payload(decode=True)
                    image_filename = os.path.join(save_folder, f"image_{num.decode()}.png")
                    with open(image_filename, 'wb') as f:
                        f.write(image_data)
                    extracted_text = pytesseract.image_to_string(Image.open(image_filename))
                    if extracted_text:
                        body += f"\n\nImage Text:\n{extracted_text}"
        else:
            body_part = email_message.get_payload(decode=True)
            if body_part:
                body = body_part.decode("utf-8", errors="ignore")

        # Combine subject and body for audio
        full_text = f"Subject: {subject}\n\nBody: {body or '(No Body)'}"

        # Generate unique filename for the audio file
        timestamp = int(time.time())
        audio_filename = f"{audio_folder}/email_{timestamp}_{num.decode()}.mp3"

        # Convert the email text to speech
        try:
            text_to_speech(full_text, audio_filename)
        except Exception as e:
            print(f"Error converting text to speech for email '{subject}': {e}")
            continue  # Skip this email if there's an error

        emails.append({
            "subject": subject,
            "body": body,
            "audio_file": audio_filename
        })

    mail.logout()
    return emails

# Send email function
def send_email(to_address, subject, body):
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = EMAIL, to_address, subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            server.send_message(msg)

            sent_emails.append({
                "to": to_address,
                "subject": subject,
                "body": body,
                "sent_time": time.strftime('%Y-%m-%d %H:%M:%S')
            })

            return True
    except smtplib.SMTPException as e:
        print(f"Error sending email: {str(e)}")
        return False

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

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/inbox')
def inbox():
    emails = fetch_and_convert_emails()
    return render_template("inbox.html", emails=emails)

@app.route('/sent')
def sent():
    return render_template('sent.html', sent_emails=sent_emails)

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if request.method == 'POST':
        to_address = request.form.get('to')
        subject = request.form.get('subject')
        body = request.form.get('body')

        if not to_address or not subject or not body:
            flash('All fields are required.', 'error')
            return render_template('compose.html')

        if send_email(to_address, subject, body):
            flash('Email sent successfully!', 'success')
            return redirect(url_for('sent'))
        else:
            flash('Error sending email. Please try again.', 'error')

    return render_template('compose.html')

@app.route("/download_audio/<path:filename>")
def download_audio(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
