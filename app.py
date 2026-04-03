from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import shutil
import subprocess
import sys
from werkzeug.utils import secure_filename
import datetime
from ripper import rip_disk, merge_disks
import threading
from concurrent.futures import ThreadPoolExecutor
from metadata_service import MetadataService

app = Flask(__name__)

# Bounded thread pool for background tasks to prevent DB locking
executor = ThreadPoolExecutor(max_workers=3)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///digibook.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

LIBRARY_DIR = 'library'
TEMP_DIR = 'temp'

# Ensure directories exist
os.makedirs(LIBRARY_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=True)
    author = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    genre = db.Column(db.String(255), nullable=True)
    cover_url = db.Column(db.String(512), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class ReadingSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    progress_percentage = db.Column(db.Float, default=0.0)
    last_accessed = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    book = db.relationship('Book', backref=db.backref('reading_sessions', cascade='all, delete-orphan', lazy=True))

class RipSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_name = db.Column(db.String(255), nullable=False, unique=True)
    current_disk = db.Column(db.Integer, default=1)
    cd_drive = db.Column(db.String(255), nullable=True)

# active_sessions replaced by RipSession model

@app.route('/')
def index():
    # Load all books from DB
    books = Book.query.order_by(Book.date_added.desc()).all()
    # List all MP3 files in the library directory that might not be in DB
    existing_files = []
    for f in os.listdir(LIBRARY_DIR):
        if f.endswith('.mp3') or f.endswith('.epub') or f.endswith('.pdf'):
            existing_files.append(f)

    # Add any missing files to DB automatically for backward compatibility
    for f in existing_files:
        if not Book.query.filter_by(filename=f).first():
            new_book = Book(filename=f, title=f)
            db.session.add(new_book)
            db.session.commit()

            filepath = os.path.join(LIBRARY_DIR, f)
            executor.submit(process_book_metadata, app.app_context(), new_book.id, filepath)

    # Re-query after adding missing
    books = Book.query.order_by(Book.date_added.desc()).all()

    # Load active reading sessions for carousel
    active_sessions = ReadingSession.query.order_by(ReadingSession.last_accessed.desc()).all()

    return render_template('index.html', books=books, active_sessions=active_sessions)

@app.route('/update_progress/<int:book_id>', methods=['POST'])
def update_progress(book_id):
    data = request.get_json()
    if not data or 'progress' not in data:
        return jsonify({'error': 'Missing progress'}), 400

    progress = float(data['progress'])
    session = ReadingSession.query.filter_by(book_id=book_id).first()

    if not session:
        session = ReadingSession(book_id=book_id, progress_percentage=progress)
        db.session.add(session)
    else:
        session.progress_percentage = progress

    db.session.commit()
    return jsonify({'success': True, 'progress': progress})

@app.route('/open/<book_name>')
def open_book(book_name):
    # The book_name passed is usually something like "My_Book.mp3"
    # To be safe against directory traversal
    book_name = secure_filename(book_name)
    file_path = os.path.abspath(os.path.join(LIBRARY_DIR, book_name))

    # Create or update Reading Session
    book = Book.query.filter_by(filename=book_name).first()
    if book:
        session = ReadingSession.query.filter_by(book_id=book.id).first()
        if not session:
            # New reading session started
            session = ReadingSession(book_id=book.id, progress_percentage=0.0)
            db.session.add(session)
        else:
            # Update last accessed
            session.last_accessed = datetime.datetime.utcnow()
        db.session.commit()

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

@app.route('/delete/<int:book_id>', methods=['POST'])
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    file_path = os.path.join(LIBRARY_DIR, book.filename)

    try:
        db.session.delete(book)
        db.session.commit()

        # Only delete file if DB commit succeeds
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting book: {e}")

    return redirect(url_for('index'))

def process_book_metadata(app_context, book_id, filepath):
    with app_context:
        book = db.session.get(Book, book_id)
        if not book:
            return

        # 1. Local Metadata
        local_metadata = MetadataService.extract_local_metadata(filepath)
        if local_metadata.get('title'):
            book.title = local_metadata['title']
        if local_metadata.get('author'):
            book.author = local_metadata['author']
        if local_metadata.get('cover_url'):
            book.cover_url = local_metadata['cover_url']

        db.session.commit()

        # 2. External API Metadata (Open Library)
        search_title = book.title or book.filename
        external_metadata = MetadataService.fetch_open_library_metadata(search_title, book.author)

        if external_metadata:
            if external_metadata.get('genre'):
                book.genre = external_metadata['genre']
            if external_metadata.get('cover_url'):
                book.cover_url = external_metadata['cover_url']
            if external_metadata.get('description'):
                book.description = external_metadata['description']
            if external_metadata.get('author') and not book.author:
                book.author = external_metadata['author']
            if external_metadata.get('title') and book.title == book.filename:
                book.title = external_metadata['title']

        db.session.commit()

@app.route('/upload_library', methods=['POST'])
def upload_library():
    if 'files' not in request.files:
        return redirect(url_for('index'))

    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return redirect(url_for('index'))

    for file in files:
        if file and file.filename:
            # Secure the filename to prevent path traversal
            safe_filename = secure_filename(file.filename)
            if not safe_filename:
                continue

            filepath = os.path.join(LIBRARY_DIR, safe_filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)

            # Simple check if book already exists
            filename_only = safe_filename
            existing_book = Book.query.filter_by(filename=filename_only).first()
            if not existing_book:
                new_book = Book(filename=filename_only, title=filename_only)
                db.session.add(new_book)
                db.session.commit() # commit so thread can read it

                # Start background thread for metadata processing using executor
                executor.submit(process_book_metadata, app.app_context(), new_book.id, filepath)

    db.session.commit() # just in case
    return redirect(url_for('index'))

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
        rip_session = RipSession.query.filter_by(book_name=book_name).first()
        if not rip_session:
            rip_session = RipSession(book_name=book_name, current_disk=1, cd_drive=cd_drive if cd_drive else None)
            db.session.add(rip_session)
        else:
            rip_session.current_disk = 1
            rip_session.cd_drive = cd_drive if cd_drive else None
        db.session.commit()

        return redirect(url_for('rip_book', book_name=book_name))
    return render_template('new.html')

@app.route('/rip/<book_name>', methods=['GET', 'POST'])
def rip_book(book_name):
    # Sanitize again just in case
    book_name = secure_filename(book_name)
    rip_session = RipSession.query.filter_by(book_name=book_name).first()
    if not rip_session:
        return redirect(url_for('index'))

    current_disk = rip_session.current_disk
    message = ""
    error = ""

    if request.method == 'POST':
        action = request.form.get('action')
        book_temp_dir = os.path.join(TEMP_DIR, book_name)

        if action == 'rip_disk':
            try:
                # Rip the disk
                rip_disk(book_temp_dir, current_disk, cd_drive=rip_session.cd_drive)
                rip_session.current_disk += 1
                db.session.commit()
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
                db.session.delete(rip_session)
                db.session.commit()

                return redirect(url_for('index'))
            except Exception as e:
                error = f"Error during merge: {str(e)}"

    return render_template('rip.html', book_name=book_name, current_disk=current_disk, message=message, error=error)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Flask debug mode must remain disabled (`debug=False`) as per memory rule
    app.run(debug=False, port=5000)
