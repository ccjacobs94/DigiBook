import sys
from unittest.mock import MagicMock

sys.modules['pydub'] = MagicMock()

import os
import subprocess
import pytest
from unittest.mock import patch, call
import ripper

def test_get_cd_drive_path_cdrom(monkeypatch):
    def mock_exists(path):
        if path == '/dev/cdrom':
            return True
        return False
    monkeypatch.setattr(os.path, 'exists', mock_exists)
    assert ripper.get_cd_drive_path() == '/dev/cdrom'

def test_get_cd_drive_path_sr0(monkeypatch):
    def mock_exists(path):
        if path == '/dev/sr0':
            return True
        return False
    monkeypatch.setattr(os.path, 'exists', mock_exists)
    assert ripper.get_cd_drive_path() == '/dev/sr0'

def test_get_cd_drive_path_none(monkeypatch):
    monkeypatch.setattr(os.path, 'exists', lambda path: False)
    assert ripper.get_cd_drive_path() is None

def test_eject_drive_success(monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, 'run', mock_run)
    ripper.eject_drive('/dev/cdrom')
    mock_run.assert_called_once_with(['eject', '/dev/cdrom'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def test_eject_drive_no_drive(monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, 'run', mock_run)
    monkeypatch.setattr(ripper, 'get_cd_drive_path', lambda: None)
    ripper.eject_drive()
    mock_run.assert_not_called()

def test_eject_drive_error(monkeypatch):
    mock_run = MagicMock(side_effect=FileNotFoundError("mock not found"))
    monkeypatch.setattr(subprocess, 'run', mock_run)
    # Should not raise exception
    ripper.eject_drive('/dev/cdrom')

def test_check_drive_ready():
    assert ripper.check_drive_ready() is True

def test_rip_disk_with_drive(monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, 'run', mock_run)

    mock_audio_segment = MagicMock()
    mock_from_wav = MagicMock(return_value=mock_audio_segment)
    monkeypatch.setattr(ripper.AudioSegment, 'from_wav', mock_from_wav)

    mock_remove = MagicMock()
    monkeypatch.setattr(os, 'remove', mock_remove)

    ripper.rip_disk('/test/output', 1, cd_drive='/dev/cdrom')

    mock_run.assert_called_once_with(['cdparanoia', '-d', '/dev/cdrom', '1-', '/test/output/disk_1.wav'], check=True)
    mock_from_wav.assert_called_once_with('/test/output/disk_1.wav')
    mock_audio_segment.export.assert_called_once_with('/test/output/disk_1.mp3', format='mp3')
    mock_remove.assert_called_once_with('/test/output/disk_1.wav')

def test_rip_disk_no_cdparanoia(monkeypatch):
    mock_run = MagicMock(side_effect=FileNotFoundError("mock not found"))
    monkeypatch.setattr(subprocess, 'run', mock_run)

    with pytest.raises(Exception, match="cdparanoia not found"):
        ripper.rip_disk('/test/output', 1, cd_drive='/dev/cdrom')

def test_rip_disk_subprocess_error(monkeypatch):
    mock_run = MagicMock(side_effect=subprocess.CalledProcessError(1, 'cmd'))
    monkeypatch.setattr(subprocess, 'run', mock_run)

    with pytest.raises(Exception, match="Error ripping CD"):
        ripper.rip_disk('/test/output', 1, cd_drive='/dev/cdrom')

def test_rip_disk_mock(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(ripper.time, 'sleep', mock_sleep)

    mock_silent = MagicMock()
    mock_audio = MagicMock()
    mock_silent.return_value = mock_audio
    monkeypatch.setattr(ripper.AudioSegment, 'silent', mock_silent)

    ripper.rip_disk('/test/output', 1, cd_drive=None)

    mock_sleep.assert_called_once_with(2)
    mock_silent.assert_called_once_with(duration=5000)
    mock_audio.export.assert_called_once_with('/test/output/disk_1.mp3', format='mp3')

def test_merge_disks_success(monkeypatch, tmp_path):
    # Setup tmp dir with fake mp3s
    (tmp_path / "disk_2.mp3").touch()
    (tmp_path / "disk_1.mp3").touch()

    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, 'run', mock_run)

    output_path = tmp_path / "merged.mp3"
    ripper.merge_disks(str(tmp_path), str(output_path))

    # Expect three calls to subprocess.run: 1 for version check, 1 for merge, 1 for VBR re-mux
    assert mock_run.call_count == 3
    temp_merged_path = str(tmp_path / "temp_merged.mp3")
    mock_run.assert_has_calls([
        call(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True),
        call(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp_path / "files.txt"), '-c', 'copy', temp_merged_path], check=True),
        call(['ffmpeg', '-y', '-i', temp_merged_path, '-write_xing', '1', '-c', 'copy', str(output_path)], check=True)
    ])

    # Check if files.txt is correctly generated
    with open(tmp_path / "files.txt", "r") as f:
        content = f.read()
    assert "file 'disk_1.mp3'" in content
    assert "file 'disk_2.mp3'" in content
    assert content.index("disk_1.mp3") < content.index("disk_2.mp3")

def test_merge_disks_no_ffmpeg(monkeypatch, tmp_path):
    mock_run = MagicMock(side_effect=FileNotFoundError("mock not found"))
    monkeypatch.setattr(subprocess, 'run', mock_run)

    with pytest.raises(Exception, match="ffmpeg not found"):
        ripper.merge_disks(str(tmp_path), str(tmp_path / "merged.mp3"))

def test_merge_disks_no_files(monkeypatch, tmp_path):
    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, 'run', mock_run)

    ripper.merge_disks(str(tmp_path), str(tmp_path / "merged.mp3"))

    # Only version check is called
    mock_run.assert_called_once_with(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def test_merge_disks_error(monkeypatch, tmp_path):
    (tmp_path / "disk_1.mp3").touch()

    def mock_run_impl(*args, **kwargs):
        if 'concat' in args[0]:
            raise subprocess.CalledProcessError(1, 'cmd')
        return MagicMock()

    mock_run = MagicMock(side_effect=mock_run_impl)
    monkeypatch.setattr(subprocess, 'run', mock_run)

    with pytest.raises(Exception, match="Failed to merge files"):
        ripper.merge_disks(str(tmp_path), str(tmp_path / "merged.mp3"))

def test_merge_disks_error_second_pass(monkeypatch, tmp_path):
    (tmp_path / "disk_1.mp3").touch()

    def mock_run_impl(*args, **kwargs):
        if '-write_xing' in args[0]:
            raise subprocess.CalledProcessError(1, 'cmd')
        return MagicMock()

    mock_run = MagicMock(side_effect=mock_run_impl)
    monkeypatch.setattr(subprocess, 'run', mock_run)

    with pytest.raises(Exception, match="Failed to merge files"):
        ripper.merge_disks(str(tmp_path), str(tmp_path / "merged.mp3"))
