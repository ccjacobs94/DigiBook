from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
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
    books = [f for f in os.listdir(LIBRARY_DIR) if f.endswith('.mp3')]
    return render_template('index.html', books=books)

@app.route('/open/<book_name>')
def open_book(book_name):
    # The book_name passed is usually something like "My_Book.mp3"
    # To be safe against directory traversal
    book_name = secure_filename(book_name)
    file_path = os.path.abspath(os.path.join(LIBRARY_DIR, book_name))

    if os.path.exists(file_path):
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", file_path])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", file_path])
            else:
                subprocess.run(["xdg-open", os.path.dirname(file_path)])
        except Exception as e:
            print(f"Error opening file location: {e}")

    return redirect(url_for('index'))

@app.route('/delete/<book_name>', methods=['POST'])
def delete_book(book_name):
    book_name = secure_filename(book_name)
    file_path = os.path.join(LIBRARY_DIR, book_name)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")

    return redirect(url_for('index'))

@app.route('/select_drive')
def select_drive():
    # Hide the main tkinter window
    root = tk.Tk()
    root.withdraw()
    # Force the window to top level
    root.attributes('-topmost', True)

    # Open directory selection dialog
    folder_path = filedialog.askdirectory(title="Select CD Drive Directory")

    # Destroy the root to clean up
    root.destroy()

    if folder_path:
        return jsonify({"path": folder_path})
    return jsonify({"path": ""})

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
