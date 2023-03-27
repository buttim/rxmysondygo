import serial
import json
import time
import os
import sys
import math
import threading
import http.server
from datetime import datetime, timedelta
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.parse import parse_qs
from pushbullet import PushBullet

hostName = "0.0.0.0"
serverPort = 5556
tipi = ['RS41', 'M20', 'M10', 'PIL', 'DFM']
data = {}
fine = False
files = []
ttgo = {}
ser = {}
dir = os.path.dirname(os.path.abspath(sys.argv[0]))
R = 6371


def distance(lat1, lon1, lat2, lon2):
    lat1 = lat1 / 180 * math.pi
    lat2 = lat2 / 180 * math.pi
    lon1 = lon1 / 180 * math.pi
    lon2 = lon2 / 180 * math.pi
    return math.acos((math.sin(lat1) * math.sin(lat2)) +
                     (math.cos(lat1) * math.cos(lat2) *
                     math.cos((lon1 - lon2)))) * R


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


class MyServer(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path == '/cfg':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = post_data.decode('utf-8')
            # print(data)
            cfg = json.loads(data)
            self.send_response(200)
            self.end_headers()
            for i in cfg:
                tipo = tipi.index(cfg[i]['type']) + 1
                cmd = f'o{{f={cfg[i]["freq"]}/tipo={tipo}}}o'
                # print(cmd,flush=True)
                ser[i].write(cmd.encode())

    def do_GET(self):
        try:
            uri = urlparse(self.path)
            params = parse_qs(uri.query)
            if uri.path == '/data':
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                start = params['from'][0] if 'from' in params else ''
                res = {
                    id: {
                        'type': sondeData['type'],
                        'freq': sondeData['freq'],
                        'frames': [x for x in sondeData['frames']
                                   if x['datetime'] > start]
                    }
                    for (id, sondeData) in data.items()
                }
                self.wfile.write(bytes(json.dumps(res, default=json_serial),
                                 "utf-8"))
            elif self.path == '/cfg':
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(bytes(json.dumps(ttgo), "utf-8"))
            elif self.path == '/':
                self.path = "web/rxmysondygo.html"
                http.server.SimpleHTTPRequestHandler.do_GET(self)
            elif self.path.strip('/') in files:
                self.path = "web" + self.path
                http.server.SimpleHTTPRequestHandler.do_GET(self)
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as x:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print("line "+str(exc_tb.tb_lineno)+": "+str(x), file=sys.stderr)
            sys.stderr.flush()


def webServerThread():
    webServer = ThreadingHTTPServer((hostName, serverPort), MyServer)
    while not fine:
        try:
            # webServer.serve_forever()
            webServer.handle_request()
        except KeyboardInterrupt:
            break
        except Exception as x:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(exc_tb.tb_lineno, x, file=sys.stderr)
            sys.stderr.flush()
    webServer.server_close()


def purge():
    global data
    d = (datetime.now() - timedelta(hours=12)).isoformat()
    data = {k: v for (k, v) in data.items() if v['frames'][-1]['datetime'] > d}


def initPushbullet():
    apiKey = os.getenv("pushbullet_apikey")
    device = os.getenv("pushbullet_device")
    while 1:
        try:
            p = PushBullet(apiKey)
            break
        except Exception:
            time.sleep(30)
            pass

    listener = None
    for d in p.devices:
        if d.device_iden == device:
            listener = d
            break
    if listener is None:
        listener = p.new_device(device)
    return p


if len(sys.argv) < 2:
    print("specificare i nomi delle porte seriali")
    exit(1)

print("inizializzazione pushbullet...")
pushbullet = initPushbullet()
print("inizializzazione pushbullet effettuata")

try:
    os.mkdir(dir+'/log')
except FileExistsError:
    pass

files = os.listdir(dir + "/web")

thread = threading.Thread(target=webServerThread)
thread.start()

try:
    data = json.load(open('dfm.json', "r"))
    print('dati di DEBUG!!!')
except Exception:
    pass
try:
    n = 0
    for i in range(len(sys.argv)-1):
        ser[sys.argv[i+1]] = (serial.Serial(sys.argv[i+1], 9600))
        n += 1
except serial.SerialException:
    print(f'La seriale {sys.argv[n+1]} non esiste?')
    fine = True
    thread.join(5)
    exit(1)

try:
    while True:
        for i in ser:
            if ser[i] is None:
                continue
            try:
                s = ser[i].readline().decode().strip()
            except serial.SerialException as x:
                print(f'Errore lettura seriale {ser[i].name}: {x}')
                ser[i] = None
                continue

            a = s.split('/')
            try:
                if len(a) < 4:
                    continue
                if a[1] not in tipi:
                    continue
                if ser[i].name not in ttgo:
                    ttgo[ser[i].name] = {'type': a[1], 'freq': float(a[2])}
                if (a[0] != '1') or float(a[4]) == 0:
                    continue
                id = a[3]
                if id == 'No data':
                    continue
                d = datetime.now().isoformat()
                lat = float(a[4])
                lon = float(a[5])
                alt = float(a[6])
                rssi = float(a[8])
                if lat < -360 or lat > 360 or lon < -90 or lon > 90:
                    continue
            except Exception:
                continue
            frame = {
                'datetime': d,
                'lat': lat,
                'lon': lon,
                'alt': alt,
                'rssi': rssi
            }
            if id not in data:  # nuova sonda
                pushbullet.push_note("rxmysondygo", f'Nuova sonda {a[1]}, {id} ({a[2]}MHz)')
                purge()
                data[id] = {'type': a[1], 'freq': a[2], 'frames': []}
            elif len(data[id]['frames']) > 0:
                lastFrame = data[id]['frames'][-1]
                try:
                    d = distance(lat, lon, lastFrame['lat'], lastFrame['lon'])
                except Exception:
                    continue
                if d > 1000:
                    continue
            data[id]['frames'].append(frame)
            with open(f'{dir}/log/{id}.log', "a") as f:
                f.write(f'{d},{lat},{lon},{alt},{rssi}\n')
except KeyboardInterrupt:
    print("Sto uscendo...")
    fine = True
    thread.join(5)
except Exception as x:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    print("line "+str(exc_tb.tb_lineno)+": "+str(x), file=sys.stderr)
    fine = True
    thread.join(5)
