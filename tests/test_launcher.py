import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as launcher


class LauncherTests(unittest.TestCase):
    def test_check_command_does_not_start_server_or_browser(self):
        with patch.object(launcher, 'prepare_environment', return_value=None), \
             patch.object(sys, 'argv', ['run.py', '--check']), \
             patch.object(launcher.subprocess, 'Popen') as process, \
             patch.object(launcher.webbrowser, 'open') as browser:
            self.assertEqual(launcher.main(), 0)
        process.assert_not_called()
        browser.assert_not_called()

    def test_existing_instance_does_not_start_duplicate(self):
        project = hashlib.sha256(str(launcher.BASE).casefold().encode()).hexdigest()[:16]
        status = {'app_id': 'aura-local', 'app_version': '2.0.0', 'project_id': project}
        with patch.object(launcher, 'prepare_environment', return_value=None), \
             patch.object(sys, 'argv', ['run.py', '--no-browser']), \
             patch.object(launcher, 'server_status', return_value=status), \
             patch.object(launcher.subprocess, 'Popen') as process:
            self.assertEqual(launcher.main(), 0)
        process.assert_not_called()

    def test_old_server_is_not_silently_reused(self):
        with patch.object(launcher, 'prepare_environment', return_value=None), \
             patch.object(sys, 'argv', ['run.py']), \
             patch.object(launcher, 'server_status', return_value={'app_id': 'aura-local', 'app_version': '4.0.0'}):
            with self.assertRaisesRegex(RuntimeError, 'precedente'):
                launcher.main()

    def test_other_project_is_not_silently_reused(self):
        with patch.object(launcher, 'prepare_environment', return_value=None), \
             patch.object(sys, 'argv', ['run.py']), \
             patch.object(launcher, 'server_status', return_value={'app_id': 'aura-local', 'app_version': '2.0.0', 'project_id': 'other'}):
            with self.assertRaisesRegex(RuntimeError, 'copia'):
                launcher.main()

    def test_matching_dependencies_do_not_run_pip_just_for_missing_stamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / '.venv'
            environment.mkdir()
            python = environment / 'python.exe'
            python.touch()
            (root / 'requirements.lock.txt').write_text('flask==3.1.3\n')
            with patch.object(launcher, 'BASE', root), patch.object(launcher, 'ENV', environment), \
                 patch.object(launcher, 'ENV_PYTHON', python), patch.object(sys, 'executable', str(python)), \
                 patch.object(launcher, 'dependencies_match', return_value=True), \
                 patch.object(launcher.subprocess, 'check_call') as pip:
                self.assertIsNone(launcher.prepare_environment())
            pip.assert_not_called()
            self.assertTrue((environment / 'requirements.sha256').exists())


if __name__ == '__main__':
    unittest.main()
