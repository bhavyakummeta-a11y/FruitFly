import unittest
try:
    import cv2
    import numpy as np
    from flight_simulator.camera_vision import detect,Observer,crop
except ImportError:
    cv2=None


@unittest.skipIf(cv2 is None,'optional requirements-camera.txt not installed')
class CameraTests(unittest.TestCase):
    def image(self):return np.zeros((400,600,3),np.uint8)

    def test_runway_converging_edges_and_center(self):
        image=self.image()
        cv2.line(image,(280,120),(100,380),(255,255,255),5)
        cv2.line(image,(320,120),(500,380),(255,255,255),5)
        r=detect(image)['runway_candidate']
        self.assertIsNotNone(r)
        self.assertLess(abs(r['center_offset']),.05)

    def test_blank_does_not_become_clear_runway(self):
        r=Observer().update(self.image(),0)
        self.assertIsNone(r['runway_candidate'])
        self.assertIsNone(r['candidate_inputs']['looming'])
        self.assertIsNone(r['candidate_inputs']['hs_left'])

    def test_round_red_fly_eye_is_not_tower(self):
        image=self.image();cv2.circle(image,(200,200),40,(0,0,255),-1)
        self.assertEqual(detect(image)['tower_candidates'],[])

    def test_elongated_eye_rejected_but_banded_tower_kept(self):
        image=self.image()
        cv2.ellipse(image,(100,180),(30,60),0,0,360,(0,0,180),-1)
        cv2.rectangle(image,(300,100),(345,180),(0,0,200),-1)
        cv2.rectangle(image,(300,130),(345,145),(170,170,190),-1)
        boxes=detect(image)['tower_candidates']
        self.assertEqual(len(boxes),1)
        self.assertGreater(boxes[0][0],250)

    def test_expansion_requires_matching_recent_frames(self):
        observer=Observer();a=self.image();b=self.image()
        cv2.rectangle(a,(200,100),(230,220),(0,0,255),-1)
        cv2.rectangle(b,(198,95),(232,235),(0,0,255),-1)
        self.assertIsNone(observer.update(a,0)['expansion_per_s'])
        r=observer.update(b,.5)
        self.assertGreater(r['candidate_inputs']['looming'],0)
        self.assertFalse(r['controls_aircraft'])
        self.assertIsNone(observer.update(b,5)['expansion_per_s'])

    def test_new_object_does_not_inherit_looming(self):
        observer=Observer();a=self.image();b=self.image()
        cv2.rectangle(a,(100,100),(130,220),(0,0,255),-1)
        cv2.rectangle(b,(400,100),(450,300),(0,0,255),-1)
        observer.update(a,0)
        self.assertIsNone(observer.update(b,.5)['expansion_per_s'])

    def test_live_reader_only_gets_screenshot_and_records_observation(self):
        from http.server import BaseHTTPRequestHandler,HTTPServer
        from threading import Thread
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        import json
        from flight_simulator.camera_vision import main
        requests=[]
        payload=cv2.imencode('.png',self.image())[1].tobytes()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200);self.end_headers();self.wfile.write(payload)
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with TemporaryDirectory() as d,patch('sys.argv',['camera','--httpd',str(server.server_port),'--seconds','.1','--headless','--synthetic-port','0','--output',d]):
                self.assertEqual(main(),0)
                r=json.loads((Path(d)/'observations.jsonl').read_text().splitlines()[0])
                self.assertFalse(r['controls_aircraft'])
                self.assertEqual(requests,['/screenshot?type=png'])
        finally:
            server.shutdown();worker.join();server.server_close()

    def test_crop_removes_cockpit(self):
        image=self.image();cv2.rectangle(image,(100,260),(130,390),(0,0,255),-1)
        self.assertEqual(detect(crop(image,[0,0,1,.5]))['tower_candidates'],[])


if __name__=='__main__':unittest.main()
