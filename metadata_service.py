import os
import requests
import ebooklib
from ebooklib import epub
from PyPDF2 import PdfReader

class MetadataService:
    @staticmethod
    def extract_local_metadata(filepath):
        """Extracts basic metadata from EPUB or PDF files."""
        metadata = {'title': None, 'author': None, 'cover_url': None}

        try:
            if filepath.lower().endswith('.epub'):
                book = epub.read_epub(filepath)
                titles = book.get_metadata('DC', 'title')
                authors = book.get_metadata('DC', 'creator')

                if titles:
                    metadata['title'] = titles[0][0]
                if authors:
                    metadata['author'] = authors[0][0]

                # Extract cover
                for item in book.get_items():
                    if item.get_type() == ebooklib.ITEM_COVER or (item.get_type() == ebooklib.ITEM_IMAGE and 'cover' in item.get_name().lower()):
                        cover_content = item.get_content()
                        if cover_content:
                            # Save to a static directory
                            cover_dir = os.path.join('static', 'covers')
                            os.makedirs(cover_dir, exist_ok=True)
                            base_name = os.path.basename(filepath)
                            safe_name = "".join([c for c in base_name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                            cover_filename = f"{safe_name.replace(' ', '_')}_cover.jpg"
                            cover_path = os.path.join(cover_dir, cover_filename)

                            with open(cover_path, 'wb') as f:
                                f.write(cover_content)

                            metadata['cover_url'] = f"/static/covers/{cover_filename}"
                            break

            elif filepath.lower().endswith('.pdf'):
                reader = PdfReader(filepath)
                info = reader.metadata
                if info:
                    if info.title:
                        metadata['title'] = info.title
                    if info.author:
                        metadata['author'] = info.author
        except Exception as e:
            print(f"Error parsing local metadata for {filepath}: {e}")

        return metadata

    @staticmethod
    def fetch_open_library_metadata(title, author=None):
        """Fetches metadata asynchronously from Open Library API."""
        try:
            query = f"title={requests.utils.quote(title)}"
            if author:
                query += f"&author={requests.utils.quote(author)}"

            url = f"https://openlibrary.org/search.json?{query}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                docs = data.get('docs', [])
                if docs:
                    book_data = docs[0]

                    # Extract cover URL
                    cover_url = None
                    if 'cover_i' in book_data:
                        cover_id = book_data['cover_i']
                        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

                    return {
                        'description': None, # Search API doesn't return full desc, would need works API
                        'genre': book_data.get('subject', [''])[0] if book_data.get('subject') else None,
                        'cover_url': cover_url,
                        'author': book_data.get('author_name', [''])[0] if book_data.get('author_name') else author,
                        'title': book_data.get('title', title)
                    }
        except Exception as e:
            print(f"Error fetching Open Library metadata: {e}")

        return None
