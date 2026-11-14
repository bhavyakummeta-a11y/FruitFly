"""Session logger video recording: drives FlightGear's own recorder over its web server.

A fake FlightGear property server stands in for fgfs (no window opens).
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flight_simulator import session  # noqa: E402


class FakeFG(BaseHTTPRequestHandler):
    props = {}
    commands = []
    works = True

    def log_message(self, *a):
        pass

    def reply(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/run.cgi':
            cmd = parse_qs(url.query)['value'][0]
            FakeFG.commands.append(cmd)
            if cmd == 'video-start' and FakeFG.works:
                FakeFG.props['/sim/video/is-encoding'] = True
                FakeFG.props['/sim/video/encoding-path'] = FakeFG.props['/sim/video/directory'] + '\\fgvideo-1.mkv'
            elif cmd == 'video-start':
                FakeFG.props['/sim/video/error'] = 'codec not found'
            elif cmd == 'video-stop':
                FakeFG.props['/sim/video/is-encoding'] = False
            return self.reply({})
        prop = url.path[len('/json'):]
        if prop not in FakeFG.props:            # FlightGear: missing node -> 404
            self.send_error(404)
            return
        self.reply({'value': FakeFG.props[prop]})

    def do_POST(self):
        value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))['value']
        FakeFG.props[self.path[len('/json'):]] = value
        self.reply({})


class SessionVideo(unittest.TestCase):
    def setUp(self):
        FakeFG.props, FakeFG.commands, FakeFG.works = {'/sim/sceneryloaded': False}, [], True
        self.fg = HTTPServer(('127.0.0.1', 0), FakeFG)
        threading.Thread(target=self.fg.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = mock.patch.object(session, 'VIDEO_ROOT', Path(self.tmp.name))
        self.root.start()
        s = session.Session.__new__(session.Session)
        s.httpd, s.id, s.lock, s.connected = self.fg.server_port, 'RUN-ID', threading.Lock(), True
        s.want_video, s.video_auto_done = True, False
        s.video, s.videos, s.log = {'recording': False, 'path': '', 'error': ''}, [], []
        s.event = lambda src, text: s.log.append(text)
        self.s = s

    def tearDown(self):
        self.fg.shutdown()
        self.root.stop()
        self.tmp.cleanup()

    def test_starts_once_the_scenery_has_loaded_with_crash_safe_settings(self):
        self.s._auto_video()
        self.assertEqual(FakeFG.commands, [])
        FakeFG.props['/sim/sceneryloaded'] = True
        self.s._auto_video()
        self.s._auto_video()                       # only once per session
        self.assertEqual(FakeFG.commands, ['video-start'])
        self.assertEqual(FakeFG.props['/sim/video/container'], 'mkv')
        self.assertEqual(FakeFG.props['/sim/video/codec'], 'libx264')
        folder = Path(FakeFG.props['/sim/video/directory'])
        self.assertEqual(folder, Path(self.tmp.name) / 'RUN-ID')
        self.assertTrue(folder.is_dir())
        self.assertTrue(self.s.video['recording'])
        self.assertEqual(self.s.videos, [str(folder) + '\\fgvideo-1.mkv'])
        self.assertIn('not pushed', self.s.log[-1])

    def test_button_stops_and_restarts(self):
        self.assertTrue(self.s.record('start'))
        self.assertTrue(self.s.record('stop'))
        self.assertFalse(self.s.video['recording'])
        self.assertTrue(self.s.record('start'))
        self.assertEqual(FakeFG.commands, ['video-start', 'video-stop', 'video-start'])
        self.assertFalse(self.s.record('rm -rf'))

    def test_opt_out_and_failure_are_reported(self):
        self.s.want_video = False
        FakeFG.props['/sim/sceneryloaded'] = True
        self.s._auto_video()
        self.assertEqual(FakeFG.commands, [])
        FakeFG.works = True
        self.s.want_video = True
        FakeFG.works = False
        self.assertFalse(self.s.record('start'))
        self.assertEqual(self.s.video['error'], 'codec not found')
        self.assertIn('codec not found', self.s.log[-1])


if __name__ == '__main__':
    unittest.main()
