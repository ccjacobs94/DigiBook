from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
import os
import shutil
import subprocess
import sys
import tkinter as tk
import sqlite3
from tkinter import filedialog
import requests
from werkzeug.utils import secure_filename
from ripper import rip_disk, merge_disks, eject_drive, check_drive_ready
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TDRC, APIC, COMM, TXXX, error as MutagenError

app = Flask(__name__)

LIBRARY_DIR = 'library'
TEMP_DIR = 'temp'
DATA_DIR = 'data'
DB_PATH = os.path.join(DATA_DIR, 'metadata.db')

# Ensure directories exist
os.makedirs(LIBRARY_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Simple in-memory session manager to track disk number per audiobook
active_sessions = {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            book_name TEXT PRIMARY KEY,
            position REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/progress/<book_name>', methods=['GET'])
def get_progress(book_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT position FROM progress WHERE book_name = ?', (book_name,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify({'position': row['position']})
    return jsonify({'position': 0})

@app.route('/api/progress/<book_name>', methods=['POST'])
def save_progress(book_name):
    try:
        data = request.get_json()
        position = data.get('position', 0)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO progress (book_name, position)
            VALUES (?, ?)
            ON CONFLICT(book_name) DO UPDATE SET position=excluded.position
        ''', (book_name, position))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Error saving progress: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/progress_all', methods=['GET'])
def get_all_progress():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT book_name, position FROM progress')
    rows = cursor.fetchall()
    conn.close()

    progress_dict = {row['book_name']: row['position'] for row in rows}
    return jsonify(progress_dict)

@app.route('/sw.js')
def service_worker():
    return send_from_directory('.', 'sw.js', mimetype='application/javascript')


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

def get_book_metadata(filename, file_path):
    title = filename.replace('.mp3', '').replace('.m4b', '')
    author = ''
    year = ''

    try:
        if filename.endswith('.mp3'):
            audio = MP3(file_path)
            tags = audio.tags if audio.tags else {}

            if tags.getall('TIT2'):
                title = str(tags.getall('TIT2')[0].text[0])
            if tags.getall('TPE1'):
                author = str(tags.getall('TPE1')[0].text[0])
            if tags.getall('TDRC'):
                year = str(tags.getall('TDRC')[0].text[0])
        elif filename.endswith('.m4b'):
            audio = MP4(file_path)
            tags = audio.tags if audio.tags else {}

            if tags.get('\xa9nam'):
                title = str(tags.get('\xa9nam')[0])
            if tags.get('\xa9ART'):
                author = str(tags.get('\xa9ART')[0])
            if tags.get('\xa9day'):
                year = str(tags.get('\xa9day')[0])
    except Exception as e:
        pass

    return {'title': title, 'author': author, 'year': year}

@app.route('/api/metadata/<book_name>')
def api_get_metadata(book_name):
    # secure_filename removes spaces, so we just use basename to prevent directory traversal
    safe_book_name = os.path.basename(book_name)
    file_path = os.path.join(LIBRARY_DIR, safe_book_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'Not found'}), 404

    metadata = get_book_metadata(safe_book_name, file_path)
    return jsonify(metadata)


@app.route('/')
def index():
    sort_by = request.args.get('sort_by', 'date_added')
    order = request.args.get('order', 'desc')

    # List all MP3 and M4B files in the library directory
    book_files = [f for f in os.listdir(LIBRARY_DIR) if f.endswith('.mp3') or f.endswith('.m4b')]

    books = []
    for f in book_files:
        file_path = os.path.join(LIBRARY_DIR, f)
        date_added = os.path.getctime(file_path)

        meta = get_book_metadata(f, file_path)

        books.append({
            'filename': f,
            'title': meta['title'],
            'author': meta['author'],
            'year': meta['year'],
            'date_added': date_added
        })

    # Sort books
    reverse = order == 'desc'

    if sort_by == 'title':
        books.sort(key=lambda x: x['title'].lower(), reverse=reverse)
    elif sort_by == 'author':
        books.sort(key=lambda x: x['author'].lower(), reverse=reverse)
    elif sort_by == 'year':
        books.sort(key=lambda x: str(x['year']), reverse=reverse)
    else: # Default to date_added
        books.sort(key=lambda x: x['date_added'], reverse=reverse)

    return render_template('index.html', books=books, current_sort=sort_by, current_order=order)

@app.route('/cover/<book_name>')
def get_cover(book_name):
    book_name = secure_filename(book_name)
    file_path = os.path.join(LIBRARY_DIR, book_name)

    if os.path.exists(file_path):
        try:
            if book_name.endswith('.mp3'):
                audio = MP3(file_path)
                apic_tags = audio.tags.getall('APIC') if audio.tags else []
                if apic_tags:
                    cover_data = apic_tags[0].data
                    mime_type = apic_tags[0].mime
                    from flask import Response
                    return Response(cover_data, mimetype=mime_type)
            elif book_name.endswith('.m4b'):
                audio = MP4(file_path)
                covr_tags = audio.tags.get('covr') if audio.tags else []
                if covr_tags:
                    cover_data = covr_tags[0]
                    mime_type = 'image/jpeg' if covr_tags[0].imageformat == MP4Cover.FORMAT_JPEG else 'image/png'
                    from flask import Response
                    return Response(cover_data, mimetype=mime_type)
        except Exception as e:
            print(f"Error reading cover from {book_name}: {e}")

    # Return a 1x1 transparent pixel or empty response if no cover
    return "", 404

@app.route('/audio/<book_name>')
def get_audio(book_name):
    file_path = os.path.join(LIBRARY_DIR, book_name)
    if os.path.exists(file_path):
        mimetype = 'audio/mp4' if book_name.endswith('.m4b') else 'audio/mpeg'
        return send_from_directory(LIBRARY_DIR, book_name, mimetype=mimetype)
    return "", 404

@app.route('/api/chapters/<book_name>')
def get_chapters(book_name):
    file_path = os.path.join(LIBRARY_DIR, book_name)
    if not os.path.exists(file_path):
        return jsonify([])

    chapters = []
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_chapters', file_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        data = result.stdout
        if data:
            import json
            parsed = json.loads(data)
            for chap in parsed.get('chapters', []):
                start_time = float(chap.get('start_time', 0))
                title = chap.get('tags', {}).get('title', f"Chapter {chap.get('id', 0) + 1}")
                chapters.append({'start_time': start_time, 'title': title})
    except Exception as e:
        print(f"Error reading chapters: {e}")

    return jsonify(chapters)

@app.route('/listen/<book_name>')
def listen_book(book_name):
    file_path = os.path.join(LIBRARY_DIR, book_name)
    if os.path.exists(file_path):
        return render_template('listen.html', book_name=book_name)
    return redirect(url_for('index'))

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

@app.route('/api/upload', methods=['POST'])
def api_upload():
    raw_book_name = request.form.get('book_name', '').strip()
    book_name = secure_filename(raw_book_name)
    if not book_name:
        book_name = "Untitled_Audiobook"

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'status': 'error', 'message': 'No files uploaded'}), 400

    book_temp_dir = os.path.join(TEMP_DIR, book_name)
    os.makedirs(book_temp_dir, exist_ok=True)

    saved_files = []
    for file in files:
        if file and file.filename.lower().endswith(('.mp3', '.m4a', '.m4b')):
            filename = secure_filename(file.filename)
            file_path = os.path.join(book_temp_dir, filename)
            file.save(file_path)
            saved_files.append(filename)

    if not saved_files:
        return jsonify({'status': 'error', 'message': 'No valid audio files uploaded'}), 400

    author = request.form.get('author', '').strip()
    year = request.form.get('year', '').strip()
    cover_url = request.form.get('cover_url', '').strip()
    isbn = request.form.get('isbn', '').strip()
    description = request.form.get('description', '').strip()

    active_sessions[book_name] = {
        'current_disk': 1,
        'original_title': raw_book_name,
        'author': author,
        'year': year,
        'cover_url': cover_url,
        'isbn': isbn,
        'description': description
    }

    # We will trigger the merge here
    try:
        output_format = request.form.get('output_format', '.mp3')
        if output_format not in ['.mp3', '.m4b']:
            output_format = '.mp3'
        output_file = os.path.join(LIBRARY_DIR, f"{book_name}{output_format}")
        merge_disks(book_temp_dir, output_file, output_format=output_format)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Error during merge: {str(e)}"}), 500
    finally:
        shutil.rmtree(book_temp_dir, ignore_errors=True)

    redirect_url = url_for('edit_metadata', book_name=f"{book_name}{output_format}", original_title=raw_book_name)
    return jsonify({'status': 'success', 'redirect_url': redirect_url})

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

        # Capture metadata if provided by search
        author = request.form.get('author', '').strip()
        year = request.form.get('year', '').strip()
        cover_url = request.form.get('cover_url', '').strip()
        isbn = request.form.get('isbn', '').strip()
        description = request.form.get('description', '').strip()

        active_sessions[book_name] = {
            'current_disk': 1,
            'cd_drive': cd_drive if cd_drive else None,
            'original_title': raw_book_name if raw_book_name else "Untitled Audiobook",
            'author': author,
            'year': year,
            'cover_url': cover_url,
            'isbn': isbn,
            'description': description
        }

        return redirect(url_for('rip_book', book_name=book_name))
    return render_template('new.html')

@app.route('/api/auto_rip/<book_name>', methods=['POST'])
def auto_rip(book_name):
    book_name = secure_filename(book_name)
    if book_name not in active_sessions:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404

    session_data = active_sessions[book_name]
    current_disk = session_data['current_disk']
    cd_drive = session_data.get('cd_drive')
    book_temp_dir = os.path.join(TEMP_DIR, book_name)

    if not check_drive_ready(cd_drive):
        return jsonify({'status': 'waiting', 'message': 'Waiting for disk...'})

    try:
        # Rip the disk
        rip_disk(book_temp_dir, current_disk, cd_drive=cd_drive)
        active_sessions[book_name]['current_disk'] += 1
        new_disk = current_disk + 1

        # Eject the disk after successful rip
        eject_drive(cd_drive=cd_drive)

        return jsonify({'status': 'success', 'current_disk': new_disk, 'message': f'Successfully ripped Disk {current_disk}.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
            original_title = active_sessions[book_name].get('original_title', book_name)
            output_format = request.form.get('output_format', '.mp3')
            if output_format not in ['.mp3', '.m4b']:
                output_format = '.mp3'
            try:
                # Merge disks and save to library
                output_file = os.path.join(LIBRARY_DIR, f"{book_name}{output_format}")
                merge_disks(book_temp_dir, output_file, output_format=output_format)
                return redirect(url_for('edit_metadata', book_name=f"{book_name}{output_format}", original_title=original_title))
            except Exception as e:
                error = f"Error during merge: {str(e)}"
            finally:
                # Clean up temp folder
                shutil.rmtree(book_temp_dir, ignore_errors=True)
                # DO NOT pop active_sessions yet, we need it for metadata
                # active_sessions.pop(book_name, None)

    return render_template('rip.html', book_name=book_name, current_disk=current_disk, message=message, error=error)

@app.route('/metadata/<book_name>', methods=['GET', 'POST'])
def edit_metadata(book_name):
    book_name = secure_filename(book_name)
    # The URL may or may not include the extension. Default to .mp3 if missing
    if not book_name.endswith('.mp3') and not book_name.endswith('.m4b'):
        book_name += '.mp3'

    output_file = os.path.join(LIBRARY_DIR, book_name)
    is_m4b = book_name.endswith('.m4b')

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

        if is_m4b:
            audio = MP4(output_file)
            if audio.tags is None:
                audio.add_tags()

            if title: audio.tags['\xa9nam'] = [title]
            if author: audio.tags['\xa9ART'] = [author]
            if narrator: audio.tags['\xa9nrt'] = [narrator] # Custom for narrator might vary, standard MP4 is \xa9nrt or just artist
            if year: audio.tags['\xa9day'] = [year]
            if description: audio.tags['desc'] = [description]
            if isbn: audio.tags['----:com.apple.iTunes:ISBN'] = [isbn.encode('utf-8')]

            if cover_url:
                try:
                    resp = requests.get(cover_url, timeout=5)
                    resp.raise_for_status()
                    image_format = MP4Cover.FORMAT_JPEG if 'jpeg' in resp.headers.get('Content-Type', '').lower() or 'jpg' in cover_url.lower() else MP4Cover.FORMAT_PNG
                    audio.tags['covr'] = [MP4Cover(resp.content, imageformat=image_format)]
                except Exception as e:
                    print(f"Error fetching cover image: {e}")

            audio.save()
        else:
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
        if is_m4b:
            audio = MP4(output_file)
            existing_tags = audio.tags if audio.tags else {}

            title = existing_tags.get('\xa9nam', [''])[0]
            author = existing_tags.get('\xa9ART', [''])[0]
            narrator = existing_tags.get('\xa9nrt', [''])[0]
            year = existing_tags.get('\xa9day', [''])[0]
            description = existing_tags.get('desc', [''])[0]

            isbn_raw = existing_tags.get('----:com.apple.iTunes:ISBN', [])
            isbn = isbn_raw[0].decode('utf-8') if isbn_raw else ''
        else:
            audio = MP3(output_file)
            existing_tags = audio.tags if audio.tags else {}

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

    original_title = request.args.get('original_title', book_name.replace('.mp3', '').replace('.m4b', ''))

    # Retrieve pre-filled session data if it exists, and clean up the session
    session_key = book_name.replace('.mp3', '').replace('.m4b', '')
    session_data = active_sessions.pop(session_key, {})

    # Apply defaults from search if current fields are empty or no tags exist
    if not has_tags:
        if not author: author = session_data.get('author', '')
        if not year: year = session_data.get('year', '')
        if not description: description = session_data.get('description', '')
        if not isbn: isbn = session_data.get('isbn', '')

    metadata = {
        'title': title,
        'author': author,
        'year': year,
        'narrator': narrator,
        'description': description,
        'isbn': isbn,
        'cover_url': session_data.get('cover_url', '') # Prefill from session if available
    }

    return render_template('metadata.html', book_name=book_name, metadata=metadata, original_title=original_title, has_tags=has_tags)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False, port=5000)
