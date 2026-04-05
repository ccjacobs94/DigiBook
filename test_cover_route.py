import pytest
from app import app
import os
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

@pytest.fixture
def client():
    app.config['TESTING'] = True
    import app as main_app
    main_app.LIBRARY_DIR = 'library'
    with app.test_client() as client:
        yield client

def test_cover_route(client):
    import os
    os.system('mkdir -p library')
    if not os.path.exists('library/testbook.mp3'):
        os.system('ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -q:a 9 -acodec libmp3lame library/testbook.mp3 2>/dev/null')

    audio = MP3('library/testbook.mp3', ID3=ID3)
    try:
        audio.add_tags()
    except:
        pass
    audio.tags.add(APIC(
        encoding=3,
        mime='image/jpeg',
        type=3,
        desc='Cover',
        data=b'my_fake_image_data'
    ))
    audio.save()

    response = client.get('/cover/testbook.mp3')
    assert response.status_code == 200
    assert response.data == b'my_fake_image_data'
    assert response.mimetype == 'image/jpeg'

    response2 = client.get('/cover/missing.mp3')
    assert response2.status_code == 404

def test_index_route(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'img src="/cover/testbook.mp3"' in response.data
    # Assert edit button link is correct
    assert b'href="/metadata/testbook.mp3"' in response.data
