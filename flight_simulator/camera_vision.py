"""Read-only FlightGear camera observer. Fixed forward view; obstacle tornadoes (dark funnels
under a storm sky) or the older red towers, and runway edges."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import socket
import time
import urllib.request
import cv2
import numpy as np


def detect(image):
    """Candidates only: tall saturated red regions and converging white runway edges."""
    h,w=image.shape[:2]
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    red=cv2.inRange(hsv,(0,110,65),(12,255,255)) | cv2.inRange(hsv,(170,110,65),(179,255,255))
    # Join white bands in the course towers, but not widely separated objects.
    red=cv2.morphologyEx(red,cv2.MORPH_CLOSE,np.ones((max(3,h//20),3),np.uint8))
    white=cv2.inRange(hsv,(0,0,175),(179,65,255))
    pale_band=cv2.inRange(hsv,(0,0,100),(179,120,255))
    towers=[]
    for c in cv2.findContours(red,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(c)
        fill=cv2.contourArea(c)/max(1,bw*bh)
        band=np.count_nonzero(pale_band[y:y+bh,x:x+bw])/max(1,bw*bh)
        if bw>=4 and bh>=max(15,h*.035) and bh/bw>=1.2 and (fill>.82 or (fill>.35 and band>.12)):
            towers.append([int(x),int(y),int(bw),int(bh)])
    towers.sort(key=lambda b:b[2]*b[3],reverse=True)
    white=cv2.inRange(hsv,(0,0,175),(179,65,255))
    edges=cv2.Canny(white,60,160)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,30,minLineLength=max(25,h*.18),maxLineGap=20)
    sides=[[],[]]
    # OpenCV 4 returns lines as (N,1,4), OpenCV 5 as (N,4).
    for x1,y1,x2,y2 in ([] if lines is None else np.asarray(lines).reshape(-1,4)):
        if abs(y2-y1)<h*.12:continue
        m=(x2-x1)/(y2-y1);b=x1-m*y1
        if .08<abs(m)<2.5:
            sides[int(m>0)].append((float(m),float(b),math.hypot(x2-x1,y2-y1)))
    runway=None;best=0
    for lm,lb,ll in sorted(sides[0],key=lambda v:-v[2])[:20]:
        for rm,rb,rl in sorted(sides[1],key=lambda v:-v[2])[:20]:
            yv=(rb-lb)/(lm-rm);xv=lm*yv+lb
            yb=h*.95;left=lm*yb+lb;right=rm*yb+rb
            if not (.05*h<yv<.7*h and .1*w<xv<.9*w and 0<=left<right<=w and .15*w<right-left<.95*w):continue
            score=ll+rl
            if score>best:
                best=score;center=(left+right)/2
                runway={'edges':[[left,yb,xv,yv],[right,yb,xv,yv]],
                        'center_offset':(center-w/2)/(w/2),
                        'axis_tilt_deg':math.degrees(math.atan2(xv-center,yb-yv))}
    return {'tower_candidates':towers[:20],'tornado_candidates':find_tornadoes(hsv)[:20],
            'runway_candidate':runway}


def find_tornadoes(hsv):
    """Candidates only: tall dark gray funnels, wider at the top, against a brighter sky.

    The obstacle tornadoes (tornado_shape.py) are dark, unsaturated and widest at the
    top. Rows of dark wider than 45% of the image (sea, ground, cockpit) are ignored, so
    a tornado that fills the view is not reported. Tuned on generated images only."""
    h,w=hsv.shape[:2]
    s,v=cv2.medianBlur(hsv[:,:,1],5),cv2.medianBlur(hsv[:,:,2],5)   # smooths rain streaks
    sky=float(np.median(v[:max(1,h//4)]))                           # top quarter = sky brightness
    if sky<60:return []                                             # too dark to tell
    dark=((v<sky*.72)&(s<110)).astype(np.uint8)*255
    wide=cv2.morphologyEx(dark,cv2.MORPH_OPEN,np.ones((1,max(3,int(w*.45))),np.uint8))
    mask=cv2.morphologyEx(cv2.bitwise_and(dark,cv2.bitwise_not(wide)),cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    found=[]
    for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(c)
        if bw<6 or bh<max(15,h*.035) or bh/bw<.8:continue
        widths=np.count_nonzero(mask[y:y+bh,x:x+bw],axis=1)
        third=max(1,bh//3)
        top,bottom=widths[:third].mean(),widths[-third:].mean()
        if top>=1.3*max(bottom,1) and cv2.contourArea(c)/(bw*bh)>.3:
            found.append([int(x),int(y),int(bw),int(bh)])
    return sorted(found,key=lambda b:b[2]*b[3],reverse=True)


def iou(a,b):
    x=max(a[0],b[0]);y=max(a[1],b[1]);r=min(a[0]+a[2],b[0]+b[2]);d=min(a[1]+a[3],b[1]+b[3])
    area=max(0,r-x)*max(0,d-y)
    return area/max(1,a[2]*a[3]+b[2]*b[3]-area)


class Observer:
    def __init__(self):self.previous=None

    def update(self,image,timestamp):
        result=detect(image);h,w=image.shape[:2]
        # Track the largest obstacle candidate of either kind (tornado or red tower).
        obstacles=sorted(result['tower_candidates']+result['tornado_candidates'],key=lambda b:b[2]*b[3],reverse=True)
        current=obstacles[0] if obstacles else None
        expansion=None;motion=None
        if current and self.previous:
            old,then,shape=self.previous;dt=timestamp-then
            if shape==(h,w) and .05<=dt<=1.5 and iou(current,old)>.15:
                expansion=math.log(current[3]/old[3])/dt
                motion=((current[0]+current[2]/2)-(old[0]+old[2]/2))/w/dt
        self.previous=(current,timestamp,(h,w)) if current else None
        runway=result['runway_candidate']
        offset=None if runway is None else runway['center_offset']
        # Candidate input encoding only. No brain call or aircraft command is made.
        cues={'looming':None if expansion is None else min(200,max(0,expansion)*400),
              'hs_left':None if offset is None else float(np.clip(100-100*offset,0,200)),
              'hs_right':None if offset is None else float(np.clip(100+100*offset,0,200))}
        result.update(time=timestamp,expansion_per_s=expansion,lateral_motion_per_s=motion,
                      candidate_inputs=cues,source='camera pixels',controls_aircraft=False)
        return result


def annotate(image,result,synthetic=None):
    out=image.copy()
    for x,y,w,h in result['tower_candidates']:
        cv2.rectangle(out,(x,y),(x+w,y+h),(0,140,255),2)
        cv2.putText(out,'tower candidate',(x,max(15,y-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,140,255),1)
    for x,y,w,h in result.get('tornado_candidates',[]):
        cv2.rectangle(out,(x,y),(x+w,y+h),(255,200,0),2)
        cv2.putText(out,'tornado candidate',(x,max(15,y-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,200,0),1)
    runway=result['runway_candidate']
    if runway:
        for a,b,c,d in runway['edges']:cv2.line(out,(round(a),round(b)),(round(c),round(d)),(0,255,0),2)
    panel=np.zeros((175,out.shape[1],3),np.uint8)
    cues=result['candidate_inputs']
    lines=['CAMERA OBSERVER ONLY - no aircraft commands / no brain stimulation',
           f"Tornadoes: {len(result.get('tornado_candidates',[]))} | Towers: {len(result['tower_candidates'])} | Runway: {'candidate' if runway else 'NOT DETECTED'}",
           'Candidate inputs: '+', '.join(f'{k}={v:.1f}' if v is not None else f'{k}=unknown' for k,v in cues.items())]
    expansion=result.get('expansion_per_s');motion=result.get('lateral_motion_per_s')
    if expansion is not None:lines.append(f'Tracked obstacle: expansion {expansion:+.3f}/s; lateral motion {motion:+.3f} image-width/s')
    if runway:lines.append(f"Runway image offset {runway['center_offset']:+.2f}; axis tilt {runway['axis_tilt_deg']:+.1f} deg (not aircraft heading)")
    if synthetic:
        lines.append(f"Synthetic: cross-track {synthetic.get('cross_track_m',0):+.1f} m; heading {synthetic.get('heading_error_deg',0):+.1f} deg")
    else:lines.append('Synthetic comparison: no recent telemetry')
    for i,line in enumerate(lines):cv2.putText(panel,line,(8,21+i*25),cv2.FONT_HERSHEY_SIMPLEX,.45,(230,230,230),1)
    return np.vstack([out,panel])


def fetch_frame(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/screenshot?type=png',timeout=2) as r:
        image=cv2.imdecode(np.frombuffer(r.read(),np.uint8),cv2.IMREAD_COLOR)
    if image is None:raise ValueError('FlightGear did not return a readable image')
    return image


def crop(image,roi):
    x,y,w,h=roi;ih,iw=image.shape[:2]
    return image[round(y*ih):round((y+h)*ih),round(x*iw):round((x+w)*iw)].copy()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',help='Analyze one saved screenshot instead of live FlightGear')
    p.add_argument('--httpd',type=int,default=8080)
    p.add_argument('--synthetic-port',type=int,default=5601,help='Receive comparison cues; 0 disables')
    p.add_argument('--roi',type=float,nargs=4,default=[0,0,1,1],metavar=('X','Y','W','H'),help='Normalized forward-view crop; exclude cockpit and fly')
    p.add_argument('--seconds',type=float,default=0,help='0 runs until Q or Ctrl-C')
    p.add_argument('--headless',action='store_true')
    p.add_argument('--output',default=None,help='Output directory for annotations and JSONL')
    args=p.parse_args()
    x,y,w,h=args.roi
    if not all(math.isfinite(v) for v in args.roi) or min(x,y)<0 or min(w,h)<=0 or x+w>1 or y+h>1:p.error('ROI must lie inside normalized image bounds')
    if not math.isfinite(args.seconds) or args.seconds<0:p.error('seconds must be finite and nonnegative')
    if not 1<=args.httpd<=65535:p.error('httpd must be 1..65535')
    if not 0<=args.synthetic_port<=65535:p.error('synthetic port must be 0..65535')
    out=Path(args.output or 'runs/camera-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=True)
    observer=Observer();sock=None;synthetic=None;received=-math.inf
    if args.synthetic_port and not args.image:
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:sock.bind(('127.0.0.1',args.synthetic_port))
        except OSError as exc:
            sock.close();p.error(f'Comparison port unavailable: {exc}. Close vision_view, choose another port, or use --synthetic-port 0.')
        sock.setblocking(False)
    start=time.monotonic();last_save=-math.inf
    try:
        with (out/'observations.jsonl').open('a',encoding='utf-8') as log:
            while args.seconds==0 or time.monotonic()-start<args.seconds:
                tick=time.monotonic()
                try:
                    image=cv2.imread(args.image) if args.image else fetch_frame(args.httpd)
                    if image is None:raise ValueError('Cannot read image')
                    image=crop(image,args.roi)
                    if min(image.shape[:2])<32:raise ValueError('ROI too small; use at least 32 pixels in each dimension')
                    if image.shape[1]>1280:image=cv2.resize(image,(1280,round(image.shape[0]*1280/image.shape[1])))
                    now=time.monotonic()
                    if sock:
                        for _ in range(100):
                            try:data,_=sock.recvfrom(65535)
                            except BlockingIOError:break
                            try:
                                packet=json.loads(data)
                                if isinstance(packet,dict) and packet.get('source')=='synthetic geometry':synthetic=packet;received=now
                            except (ValueError,UnicodeError):pass
                    result=observer.update(image,now-start)
                    comparison=synthetic if now-received<=2 else None
                    result.update(synthetic=comparison,roi=args.roi,image_size=list(image.shape[:2]),capture_request_s=now-tick)
                    log.write(json.dumps(result,allow_nan=False)+'\n');log.flush()
                    rendered=annotate(image,result,comparison)
                    if args.image or now-last_save>=5:
                        cv2.imwrite(str(out/f'frame-{now-start:08.2f}.png'),rendered);last_save=now
                    if not args.headless and not args.image:
                        cv2.imshow('Camera observer - Q to close',rendered)
                        if cv2.waitKey(1)&0xff==ord('q'):break
                    if args.image:break
                except (OSError,ValueError,cv2.error) as exc:
                    observer.previous=None
                    log.write(json.dumps({'error':str(exc),'time':time.monotonic()-start})+'\n');log.flush()
                    print(f'No camera observation: {exc}',flush=True)
                    if args.image:return 1
                    if not args.headless:cv2.destroyAllWindows()
                time.sleep(max(0,.5-(time.monotonic()-tick)))
    except KeyboardInterrupt:pass
    finally:
        if sock:sock.close()
        if not args.headless:cv2.destroyAllWindows()
    print(f'Camera observations saved to {out}')
    return 0


if __name__=='__main__':raise SystemExit(main())
