from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
import requests
from werkzeug.utils import secure_filename
from ripper import rip_disk, merge_disks
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TDRC, APIC, COMM, TXXX, error as MutagenError

app = Flask(__name__)

LIBRARY_DIR = 'library'
TEMP_DIR = 'temp'

# Ensure directories exist
os.makedirs(LIBRARY_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Simple in-memory session manager to track disk number per audiobook
active_sessions = {}

@app.route('/api/search_metadata')
def search_metadata():
    title = request.args.get('title', '')
    if not title:
        return jsonify([])

    try:
        resp = requests.get("https://openlibrary.org/search.json", params={'title': title, 'limit': 10}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for doc in data.get('docs', []):
            author = doc.get('author_name', [''])[0] if doc.get('author_name') else ''
            year = str(doc.get('first_publish_year', ''))
            cover_i = doc.get('cover_i')
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-S.jpg" if cover_i else ''
            cover_url_large = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else ''
            isbn = doc.get('isbn', [''])[0] if doc.get('isbn') else ''
            work_id = doc.get('key', '')
            results.append({
                'title': doc.get('title', title),
                'author': author,
                'year': year,
                'cover_url': cover_url,
                'cover_url_large': cover_url_large,
                'isbn': isbn,
                'work_id': work_id
            })
        return jsonify(results)
    except Exception as e:
        print(f"Error searching metadata: {e}")
        return jsonify([]), 500

@app.route('/api/work_description')
def work_description():
    work_id = request.args.get('work_id', '')
    if not work_id:
        return jsonify({'description': ''})

    try:
        # work_id typically looks like "/works/OL12345W"
        if not work_id.startswith('/works/'):
            work_id = f"/works/{work_id}"
        resp = requests.get(f"https://openlibrary.org{work_id}.json", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        description = data.get('description', '')
        if isinstance(description, dict):
            description = description.get('value', '')
        return jsonify({'description': description})
    except Exception as e:
        print(f"Error fetching description: {e}")
        return jsonify({'description': ''}), 500

@app.route('/')
def index():
    # List all MP3 files in the library directory
    books = [f for f in os.listdir(LIBRARY_DIR) if f.endswith('.mp3')]
    return render_template('index.html', books=books)

@app.route('/cover/<book_name>')
def get_cover(book_name):
    book_name = secure_filename(book_name)
    file_path = os.path.join(LIBRARY_DIR, book_name)

    if os.path.exists(file_path):
        try:
            audio = MP3(file_path)
            apic_tags = audio.tags.getall('APIC') if audio.tags else []
            if apic_tags:
                cover_data = apic_tags[0].data
                mime_type = apic_tags[0].mime
                from flask import Response
                return Response(cover_data, mimetype=mime_type)
        except Exception as e:
            print(f"Error reading cover from {book_name}: {e}")

    # Return a 1x1 transparent pixel or empty response if no cover
    return "", 404

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
            'cd_drive': cd_drive if cd_drive else None,
            'original_title': raw_book_name if raw_book_name else "Untitled Audiobook"
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
                original_title = active_sessions[book_name].get('original_title', book_name)
                del active_sessions[book_name]

                return redirect(url_for('edit_metadata', book_name=book_name, original_title=original_title))
            except Exception as e:
                error = f"Error during merge: {str(e)}"

    return render_template('rip.html', book_name=book_name, current_disk=current_disk, message=message, error=error)

@app.route('/metadata/<book_name>', methods=['GET', 'POST'])
def edit_metadata(book_name):
    book_name = secure_filename(book_name)
    # The URL may or may not include the .mp3 extension.
    # The home page passes the full filename including .mp3
    if not book_name.endswith('.mp3'):
        book_name += '.mp3'

    output_file = os.path.join(LIBRARY_DIR, book_name)

    if not os.path.exists(output_file):
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '')
        author = request.form.get('author', '')
        narrator = request.form.get('narrator', '')
        year = request.form.get('year', '')
        cover_url = request.form.get('cover_url', '')
        description = request.form.get('description', '')
        isbn = request.form.get('isbn', '')

        try:
            audio = MP3(output_file, ID3=ID3)
        except MutagenError:
            audio = MP3(output_file)
            audio.add_tags()

        if title:
            audio.tags.add(TIT2(encoding=3, text=title))
        if author:
            audio.tags.add(TPE1(encoding=3, text=author))
        if narrator:
            audio.tags.add(TPE2(encoding=3, text=narrator))
        if year:
            audio.tags.add(TDRC(encoding=3, text=year))
        if description:
            audio.tags.add(COMM(encoding=3, lang='eng', desc='Description', text=[description]))
        if isbn:
            audio.tags.add(TXXX(encoding=3, desc='ISBN', text=[isbn]))

        if cover_url:
            try:
                resp = requests.get(cover_url, timeout=5)
                resp.raise_for_status()
                audio.tags.add(APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Cover',
                    data=resp.content
                ))
            except Exception as e:
                print(f"Error fetching cover image: {e}")

        audio.save()
        return redirect(url_for('index'))

    # Attempt to load existing metadata
    try:
        audio = MP3(output_file)
        existing_tags = audio.tags if audio.tags else {}

        # We need a Mutagen ID3 object if MP3, else fallback
        title = existing_tags.getall('TIT2')[0].text[0] if existing_tags.getall('TIT2') else ''
        author = existing_tags.getall('TPE1')[0].text[0] if existing_tags.getall('TPE1') else ''
        narrator = existing_tags.getall('TPE2')[0].text[0] if existing_tags.getall('TPE2') else ''
        year = existing_tags.getall('TDRC')[0].text[0] if existing_tags.getall('TDRC') else ''
        description = existing_tags.getall('COMM:Description:eng')[0].text[0] if existing_tags.getall('COMM:Description:eng') else ''
        isbn = existing_tags.getall('TXXX:ISBN')[0].text[0] if existing_tags.getall('TXXX:ISBN') else ''

        has_tags = bool(title or author or narrator or year or description or isbn)

    except Exception as e:
        print(f"Error reading existing tags: {e}")
        has_tags = False
        title = author = narrator = year = description = isbn = ''

    metadata = {
        'title': title,
        'author': author,
        'year': year,
        'narrator': narrator,
        'description': description,
        'isbn': isbn,
        'cover_url': '' # Hard to pre-populate image URL from raw bytes, leave blank or let user change
    }

    original_title = request.args.get('original_title', book_name.replace('.mp3', ''))

    return render_template('metadata.html', book_name=book_name, metadata=metadata, original_title=original_title, has_tags=has_tags)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
