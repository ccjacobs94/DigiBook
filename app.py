from flask import Flask, render_template, request, redirect, url_for
import os
import shutil
from werkzeug.utils import secure_filename
from ripper import rip_disk, merge_disks

app = Flask(__name__)
LIBRARY_DIR = 'library'
TEMP_DIR = 'temp'

# Ensure directories exist
os.makedirs(LIBRARY_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Simple in-memory session manager to track disk number per audiobook
active_sessions = {}

@app.route('/')
def index():
    # List all MP3 files in the library directory
    books = []
    for f in os.listdir(LIBRARY_DIR):
        if f.endswith('.mp3'):
            books.append(f)
    return render_template('index.html', books=books)

@app.route('/new', methods=['GET', 'POST'])
def new_book():
    if request.method == 'POST':
        raw_book_name = request.form['book_name'].strip()
        book_name = secure_filename(raw_book_name)
        if not book_name:
            book_name = "Untitled_Audiobook"

        # Create a temp directory for this book
        book_temp_dir = os.path.join(TEMP_DIR, book_name)
        os.makedirs(book_temp_dir, exist_ok=True)

        # Initialize session tracking
        cd_drive = request.form.get('cd_drive', '').strip()
        active_sessions[book_name] = {
            'current_disk': 1,
            'cd_drive': cd_drive if cd_drive else None
        }

        return redirect(url_for('rip_book', book_name=book_name))
    return render_template('new.html')

@app.route('/rip/<book_name>', methods=['GET', 'POST'])
def rip_book(book_name):
    # Sanitize again just in case
    book_name = secure_filename(book_name)
    if book_name not in active_sessions:
        return redirect(url_for('index'))

    session_data = active_sessions[book_name]
    current_disk = session_data['current_disk']
    message = ""
    error = ""

    if request.method == 'POST':
        action = request.form.get('action')
        book_temp_dir = os.path.join(TEMP_DIR, book_name)

        if action == 'rip_disk':
            try:
                # Rip the disk
                rip_disk(book_temp_dir, current_disk, cd_drive=session_data.get('cd_drive'))
                active_sessions[book_name]['current_disk'] += 1
                current_disk += 1
                message = f"Successfully ripped Disk {current_disk - 1}."
            except Exception as e:
                error = str(e)

        elif action == 'finish':
            try:
                # Merge disks and save to library
                output_file = os.path.join(LIBRARY_DIR, f"{book_name}.mp3")
                merge_disks(book_temp_dir, output_file)

                # Clean up temp folder
                shutil.rmtree(book_temp_dir)
                del active_sessions[book_name]

                return redirect(url_for('index'))
            except Exception as e:
                error = f"Error during merge: {str(e)}"

    return render_template('rip.html', book_name=book_name, current_disk=current_disk, message=message, error=error)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
