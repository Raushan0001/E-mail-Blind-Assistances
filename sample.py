from flask import Flask, render_template, redirect, url_for, request, flash
import os
import imaplib
import email
import pyttsx3
import platform
import re

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flashing messages

# Function to check for unread emails
def get_unread_emails(username, password):
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')  # Connect to Gmail IMAP server
        mail.login(username, password)  # Log in with provided credentials
        mail.select('inbox')
        result, data = mail.search(None, '(UNSEEN)')  # Search for unseen emails
        if result != 'OK':
            return []

        # Process unread emails
        email_ids = data[0].split()
        unread_emails = []
        for email_id in email_ids:
            result, data = mail.fetch(email_id, '(RFC822)')
            if result != 'OK':
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            unread_emails.append(msg)

        mail.logout()
        return unread_emails
    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}")
        return []

# Function to check if the email is important based on keywords
def is_important(email_message):
    frequent_keywords = [
        'meeting', 'urgent', 'important', 'project', 'deadline', 'update', 'reminder',
        'schedule', 'invoice', 'payment', 'action required', 'notice', 'report',
        'confirmation', 'follow-up', 'request', 'support', 'error', 'alert', 'security',
        'notification', 'cancellation', 'invitation', 'event', 'news', 'change', 'critical'
    ]

    subject = email_message['subject']
    if subject is None:
        return False

    found_keywords = [keyword for keyword in frequent_keywords if keyword in subject.lower()]
    return bool(found_keywords)

# Convert important emails to audio using pyttsx3
def email_to_audio_pyttsx(email_message, audio_dir):
    subject = email_message['subject']
    
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == 'text/plain':
                body = part.get_payload(decode=True).decode()
                break
    else:
        body = email_message.get_payload(decode=True).decode()

    message = f"Subject: {subject}. Body: {body}"

    engine = pyttsx3.init()

    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)

    # Sanitize filename (remove invalid characters)
    sanitized_subject = re.sub(r'[\\/*?:"<>|]', "", subject)

    audio_file = os.path.join(audio_dir, f"{sanitized_subject}.mp3")
    engine.save_to_file(message, audio_file)
    engine.runAndWait()
    
    if platform.system() == "Windows":
        os.startfile(audio_file)
    elif platform.system() == "Darwin":  # macOS
        os.system(f"afplay {audio_file}")
    else:  # Linux
        os.system(f"xdg-open {audio_file}")

    return audio_file

# Home page to fetch emails and display important ones
@app.route('/', methods=['GET', 'POST'])
def fetch_emails():
    if request.method == 'POST':
        email_user = request.form.get('shatwikaandavarapu@gmail.com')  # Get email from the form
        email_pass = request.form.get('erus oiag itlv phrr')  # Get password from the form

        if not email_user or not email_pass:
            flash("Email or password cannot be empty")
            return render_template('index.html')

        # Fetch unread emails based on the form inputs
        unread_emails = get_unread_emails(email_user, email_pass)
        if not unread_emails:
            flash("No unread emails found or unable to fetch emails")
            return render_template('index.html')

        important_emails = [email for email in unread_emails if is_important(email)]
        
        return render_template('index.html', emails=important_emails)

    return render_template('index.html')

# Route to convert an email to audio
@app.route('/convert/<subject>', methods=['POST'])
def convert_to_audio(subject):
    email_user = request.form.get('email')
    email_pass = request.form.get('password')

    unread_emails = get_unread_emails(email_user, email_pass)
    
    for email_message in unread_emails:
        if email_message['subject'] == subject:
            audio_dir = "converted_emails_audio"
            email_to_audio_pyttsx(email_message, audio_dir)
            break

    return redirect(url_for('fetch_emails'))

if __name__ == "__main__":
    app.run(debug=True)
