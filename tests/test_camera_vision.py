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

    # Tornado obstacles under the storm weather (generated images; no FlightGear frames yet).
    def storm(self,cx=300,top_w=60,foot_w=14,top=60,horizon=250,rain=True):
        image=np.full((400,600,3),(168,165,160),np.uint8)            # gray overcast
        image[horizon:]=(92,88,80)                                    # dark sea below the horizon
        if top_w:
            funnel=np.array([[cx-top_w,top],[cx+top_w,top],[cx+foot_w,horizon+40],[cx-foot_w,horizon+40]])
            cv2.fillPoly(image,[funnel],(78,74,70))                   # wide top, narrow foot
        if rain:
            rng=np.random.default_rng(0)
            for _ in range(500):
                x,y=int(rng.integers(0,600)),int(rng.integers(0,380))
                cv2.line(image,(x,y),(x+2,y+14),(150,148,145),1)
        return image

    def test_tornado_found_in_rain_and_without(self):
        for rain in (True,False):
            boxes=detect(self.storm(rain=rain))['tornado_candidates']
            self.assertEqual(len(boxes),1)
            x,y,w,h=boxes[0]
            self.assertLess(abs(x+w/2-300),15)
            self.assertLess(abs(y-60),10)
            self.assertEqual(detect(self.storm(rain=rain))['tower_candidates'],[])

    def test_storm_sky_sea_pillar_and_hill_are_not_tornadoes(self):
        empty=self.storm(top_w=0)
        self.assertEqual(detect(empty)['tornado_candidates'],[])
        pillar=empty.copy();cv2.rectangle(pillar,(100,0),(130,399),(40,40,40),-1)   # cockpit frame: same width top and bottom
        self.assertEqual(detect(pillar)['tornado_candidates'],[])
        hill=empty.copy();cv2.fillPoly(hill,[np.array([[300,60],[305,60],[360,290],[240,290]])],(78,74,70))  # wide base
        self.assertEqual(detect(hill)['tornado_candidates'],[])
        self.assertEqual(detect((self.storm()*.25).astype(np.uint8))['tornado_candidates'],[])   # too dark to tell

    def test_approaching_tornado_gives_looming(self):
        observer=Observer()
        self.assertIsNone(observer.update(self.storm(top_w=60,foot_w=14,top=60),0)['expansion_per_s'])
        r=observer.update(self.storm(top_w=75,foot_w=17,top=25),.5)
        self.assertGreater(r['expansion_per_s'],0)
        self.assertGreater(r['candidate_inputs']['looming'],0)
        self.assertFalse(r['controls_aircraft'])

    def test_crop_removes_cockpit(self):
        image=self.image();cv2.rectangle(image,(100,260),(130,390),(0,0,255),-1)
        self.assertEqual(detect(crop(image,[0,0,1,.5]))['tower_candidates'],[])


if __name__=='__main__':unittest.main()
