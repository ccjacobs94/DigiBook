import sys
import os
import shutil
import pytest
from unittest.mock import MagicMock

# Mock pydub and tkinter before importing app
sys.modules['pydub'] = MagicMock()
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.filedialog'] = MagicMock()

import app

@pytest.fixture
def client():
    # Setup
    app.app.config['TESTING'] = True
    app.LIBRARY_DIR = 'test_library'
    app.TEMP_DIR = 'test_temp'
    os.makedirs(app.LIBRARY_DIR, exist_ok=True)
    os.makedirs(app.TEMP_DIR, exist_ok=True)

    with app.app.test_client() as client:
        yield client

    # Teardown
    if os.path.exists(app.LIBRARY_DIR):
        shutil.rmtree(app.LIBRARY_DIR)
    if os.path.exists(app.TEMP_DIR):
        shutil.rmtree(app.TEMP_DIR)

def test_index_empty(client):
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'Audiobook Digitizer' in rv.data # or whatever the title might be

def test_index_with_books(client):
    # Add a mock mp3 to the test library
    with open(os.path.join(app.LIBRARY_DIR, 'test_book.mp3'), 'w') as f:
        f.write('mock content')

    rv = client.get('/')
    assert rv.status_code == 200
    assert b'test_book.mp3' in rv.data

def test_index_sort_by_title(client):
    with open(os.path.join(app.LIBRARY_DIR, 'A_book.mp3'), 'w') as f:
        f.write('mock content')
    with open(os.path.join(app.LIBRARY_DIR, 'B_book.mp3'), 'w') as f:
        f.write('mock content')

    rv = client.get('/?sort_by=title&order=asc')
    assert rv.status_code == 200

    # We should see A_book before B_book
    data = rv.data.decode('utf-8')
    assert data.find('A_book.mp3') < data.find('B_book.mp3')

def test_index_sort_by_title_desc(client):
    with open(os.path.join(app.LIBRARY_DIR, 'A_book.mp3'), 'w') as f:
        f.write('mock content')
    with open(os.path.join(app.LIBRARY_DIR, 'B_book.mp3'), 'w') as f:
        f.write('mock content')

    rv = client.get('/?sort_by=title&order=desc')
    assert rv.status_code == 200

    data = rv.data.decode('utf-8')
    assert data.find('B_book.mp3') < data.find('A_book.mp3')

def test_new_book_get(client):
    rv = client.get('/new')
    assert rv.status_code == 200
    assert b'<form' in rv.data

def test_new_book_post(client):
    rv = client.post('/new', data={'book_name': 'New Book', 'cd_drive': '/dev/cdrom'})
    assert rv.status_code == 302
    assert '/rip/New_Book' in rv.headers['Location']
    assert 'New_Book' in app.active_sessions
    assert app.active_sessions['New_Book']['current_disk'] == 1
    assert app.active_sessions['New_Book']['cd_drive'] == '/dev/cdrom'
    assert os.path.exists(os.path.join(app.TEMP_DIR, 'New_Book'))

def test_delete_book(client):
    # Add a mock mp3 to the test library
    test_file_path = os.path.join(app.LIBRARY_DIR, 'to_delete.mp3')
    with open(test_file_path, 'w') as f:
        f.write('mock content')

    assert os.path.exists(test_file_path)

    rv = client.post('/delete/to_delete.mp3')
    assert rv.status_code == 302
    assert rv.headers['Location'] == '/'
    assert not os.path.exists(test_file_path)

def test_select_drive(client):
    # We mocked tkinter.filedialog so askdirectory needs a return value
    app.filedialog.askdirectory.return_value = '/mock/dir'
    rv = client.get('/select_drive')
    assert rv.status_code == 200
    assert rv.json == {'path': '/mock/dir'}

def test_open_book_redirects(client):
    rv = client.get('/open/some_book.mp3')
    assert rv.status_code == 302
    assert rv.headers['Location'] == '/'

def test_rip_book_redirects_if_not_in_session(client):
    rv = client.get('/rip/not_a_session')
    assert rv.status_code == 302
    assert rv.headers['Location'] == '/'

def test_rip_book_get(client):
    app.active_sessions['Test_Book'] = {'current_disk': 1, 'cd_drive': '/dev/cdrom'}
    rv = client.get('/rip/Test_Book')
    assert rv.status_code == 200
    assert b'Test_Book' in rv.data

def test_rip_book_post_rip_disk(client):
    app.active_sessions['Test_Book'] = {'current_disk': 1, 'cd_drive': '/dev/cdrom'}

    # Mock rip_disk
    app.rip_disk = MagicMock()

    rv = client.post('/rip/Test_Book', data={'action': 'rip_disk'})
    assert rv.status_code == 200
    assert b'Successfully ripped Disk 1' in rv.data
    assert app.active_sessions['Test_Book']['current_disk'] == 2

def test_rip_book_post_finish(client):
    app.active_sessions['Test_Book'] = {'current_disk': 2, 'cd_drive': '/dev/cdrom', 'original_title': 'Test_Book'}
    book_temp_dir = os.path.join(app.TEMP_DIR, 'Test_Book')
    os.makedirs(book_temp_dir, exist_ok=True)

    # Mock merge_disks
    app.merge_disks = MagicMock()

    rv = client.post('/rip/Test_Book', data={'action': 'finish'})
    assert rv.status_code == 302
    assert '/metadata/Test_Book' in rv.headers['Location']
    assert 'Test_Book' in app.active_sessions  # metadata session is preserved now
    assert not os.path.exists(book_temp_dir)

def test_new_book_empty_name(client):
    rv = client.post('/new', data={'book_name': '', 'cd_drive': ''})
    assert rv.status_code == 302
    assert '/rip/Untitled_Audiobook' in rv.headers['Location']
    assert 'Untitled_Audiobook' in app.active_sessions

def test_delete_book_error(client, monkeypatch):
    test_file_path = os.path.join(app.LIBRARY_DIR, 'error_delete.mp3')
    with open(test_file_path, 'w') as f:
        f.write('mock content')

    # Mock os.remove to raise exception
    def mock_remove(path):
        raise Exception("Mock error")

    monkeypatch.setattr(os, "remove", mock_remove)

    rv = client.post('/delete/error_delete.mp3')
    assert rv.status_code == 302
    assert rv.headers['Location'] == '/'
    assert os.path.exists(test_file_path) # still exists because error

def test_open_book_error(client):
    test_file_path = os.path.join(app.LIBRARY_DIR, 'error_open.mp3')
    with open(test_file_path, 'w') as f:
        f.write('mock content')

    app.subprocess.run = MagicMock(side_effect=Exception("Mock open error"))
    rv = client.get('/open/error_open.mp3')
    assert rv.status_code == 302
    assert rv.headers['Location'] == '/'

def test_auto_rip_success(client):
    app.active_sessions['Test_Auto_Book'] = {'current_disk': 1, 'cd_drive': '/dev/cdrom'}

    app.check_drive_ready = MagicMock(return_value=True)
    app.rip_disk = MagicMock()
    app.eject_drive = MagicMock()

    rv = client.post('/api/auto_rip/Test_Auto_Book')
    assert rv.status_code == 200
    assert rv.json['status'] == 'success'
    assert rv.json['current_disk'] == 2
    assert app.active_sessions['Test_Auto_Book']['current_disk'] == 2

    app.rip_disk.assert_called_once()
    app.eject_drive.assert_called_once()

def test_auto_rip_waiting(client):
    app.active_sessions['Test_Auto_Book'] = {'current_disk': 1, 'cd_drive': '/dev/cdrom'}
    app.check_drive_ready = MagicMock(return_value=False)

    rv = client.post('/api/auto_rip/Test_Auto_Book')
    assert rv.status_code == 200
    assert rv.json['status'] == 'waiting'
    assert app.active_sessions['Test_Auto_Book']['current_disk'] == 1

def test_auto_rip_error(client):
    app.active_sessions['Test_Auto_Book_Err'] = {'current_disk': 1, 'cd_drive': '/dev/cdrom'}

    app.check_drive_ready = MagicMock(return_value=True)
    app.rip_disk = MagicMock(side_effect=Exception("Mock rip error"))
    app.eject_drive = MagicMock()

    rv = client.post('/api/auto_rip/Test_Auto_Book_Err')
    assert rv.status_code == 500
    assert rv.json['status'] == 'error'
    assert 'Mock rip error' in rv.json['message']
    assert app.active_sessions['Test_Auto_Book_Err']['current_disk'] == 1 # didn't increment

    app.eject_drive.assert_not_called()

def test_rip_book_post_rip_disk_error(client):
    app.active_sessions['Test_Book_Err'] = {'current_disk': 1, 'cd_drive': '/dev/cdrom'}
    app.rip_disk = MagicMock(side_effect=Exception("Mock rip error"))

    rv = client.post('/rip/Test_Book_Err', data={'action': 'rip_disk'})
    assert rv.status_code == 200
    assert b'Mock rip error' in rv.data
    assert app.active_sessions['Test_Book_Err']['current_disk'] == 1 # didn't increment

def test_rip_book_post_finish_error(client):
    app.active_sessions['Test_Book_Err2'] = {'current_disk': 2, 'cd_drive': '/dev/cdrom'}
    book_temp_dir = os.path.join(app.TEMP_DIR, 'Test_Book_Err2')
    os.makedirs(book_temp_dir, exist_ok=True)

    app.merge_disks = MagicMock(side_effect=Exception("Mock merge error"))

    rv = client.post('/rip/Test_Book_Err2', data={'action': 'finish'})
    assert rv.status_code == 200
    assert b'Error during merge: Mock merge error' in rv.data
    assert 'Test_Book_Err2' in app.active_sessions # session is preserved now even on error since we wait to pop in metadata

def test_select_drive_none(client):
    app.filedialog.askdirectory.return_value = ''
    rv = client.get('/select_drive')
    assert rv.status_code == 200
    assert rv.json == {'path': ''}

def test_open_book_sys_platform(client, monkeypatch):
    # Test sys.platform branches
    test_file_path = os.path.join(app.LIBRARY_DIR, 'sys_test.mp3')
    with open(test_file_path, 'w') as f:
        f.write('mock content')

    app.subprocess.run = MagicMock()

    # Windows
    monkeypatch.setattr(sys, "platform", "win32")
    client.get('/open/sys_test.mp3')
    app.subprocess.run.assert_called_with(["explorer", "/select,", os.path.abspath(test_file_path)])

    # Mac
    monkeypatch.setattr(sys, "platform", "darwin")
    client.get('/open/sys_test.mp3')
    app.subprocess.run.assert_called_with(["open", "-R", os.path.abspath(test_file_path)])
