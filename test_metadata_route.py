import pytest
from app import app
import os
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TDRC

@pytest.fixture
def client():
    app.config['TESTING'] = True
    import app as main_app
    main_app.LIBRARY_DIR = 'library'
    with app.test_client() as client:
        yield client

def test_metadata_route(client):
    os.system('mkdir -p library')
    if not os.path.exists('library/test_meta.mp3'):
        os.system('ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -q:a 9 -acodec libmp3lame library/test_meta.mp3 2>/dev/null')

    # Add tags
    audio = MP3('library/test_meta.mp3', ID3=ID3)
    try:
        audio.add_tags()
    except:
        pass
    audio.tags.add(TIT2(encoding=3, text='Existing Title'))
    audio.tags.add(TPE1(encoding=3, text='Existing Author'))
    audio.tags.add(TPE2(encoding=3, text='Existing Narrator'))
    audio.tags.add(TDRC(encoding=3, text='2024'))
    audio.save()

    # Test route GET
    response = client.get('/metadata/test_meta')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert 'value="Existing Title"' in html
    assert 'value="Existing Author"' in html
    assert 'value="Existing Narrator"' in html
    assert 'value="2024"' in html
