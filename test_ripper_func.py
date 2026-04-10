import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys

# Mock AudioSegment and pydub before importing ripper
mock_pydub = MagicMock()
sys.modules['pydub'] = mock_pydub
sys.modules['pydub.AudioSegment'] = mock_pydub.AudioSegment

import ripper

class TestRipper(unittest.TestCase):
    @patch('os.listdir')
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_merge_disks_filtering_and_sorting(self, mock_file, mock_run, mock_listdir):
        # Mocking listdir to return unsorted and mixed files
        mock_listdir.return_value = ['disk_2.mp3', 'notes.txt', 'disk_1.mp3', 'disk_10.mp3']

        # Mock ffmpeg -version to avoid error
        mock_run.return_value = MagicMock(returncode=0)

        # Calling merge_disks
        temp_dir = 'fake_temp'
        output_file = 'fake_output.mp3'

        ripper.merge_disks(temp_dir, output_file)

        # Check if the correct files were written to files.txt in the correct order
        # The file content should be:
        # file 'disk_1.mp3'\n
        # file 'disk_2.mp3'\n
        # file 'disk_10.mp3'\n

        # Get all calls to write
        write_calls = mock_file().write.call_args_list
        written_content = "".join(call.args[0] for call in write_calls)

        expected_content = "file 'disk_1.mp3'\nfile 'disk_2.mp3'\nfile 'disk_10.mp3'\n"
        self.assertTrue(expected_content in written_content)

if __name__ == '__main__':
    unittest.main()
