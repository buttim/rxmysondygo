import serial
import json
import os
import sys
import time
import threading
import http.server
from datetime import datetime
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.parse import parse_qs


hostName = "0.0.0.0"
serverPort = 5556
data = {}
fine = False
files = []


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))


class MyServer(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        try:
            uri = urlparse(self.path)
            params = parse_qs(uri.query)
            if uri.path == '/data':
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                start = params['from'][0] if 'from' in params else ''
                # print(data,flush=True)
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
            webServer.serve_forever()
        except KeyboardInterrupt:
            break
        except Exception as x:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(exc_tb.tb_lineno, x, file=sys.stderr)
            sys.stderr.flush()
    webServer.server_close()


if len(sys.argv) < 2:
    print("specificare i nomi delle porte seriali")
    exit(1)

files = os.listdir(os.getcwd() + "/web")

t = threading.Thread(target=webServerThread)
t.start()

isFile = False
separator = '/'
try:
    if False and len(sys.argv) == 2:
        try:
            print(os.stat(sys.argv[1]))
            isFile = True
            separator = ','
        except FileNotFoundError:
            isFile = False
            separator = '/'

    n = 0
    ser = []
    for i in range(len(sys.argv)-1):
        ser.append(open(sys.argv[i+1], "r") if isFile
                   else serial.Serial(sys.argv[i+1], 9600))
        n += 1
    if isFile:
        ser[0].readline()  # butta via intestazione
    while True:
        for i in range(n):
            s = ser[i].readline()
            if not isFile:
                s = s.decode()
            s = s.strip()
            if s == '':
                break
            a = s.split(separator)
            if isFile:
                id = a[1]
                frame = {
                    'datetime': a[0],
                    'lat': float(a[3]),
                    'lon': float(a[4]),
                    'alt': float(a[5]),
                }
                print(frame)
                time.sleep(0.1)
            else:
                if (a[0] != '1'):
                    continue
                id = a[3]
                if id == 'No data':
                    continue
                frame = {
                    'datetime': datetime.now().isoformat() + 'Z',
                    'lat': float(a[4]),
                    'lon': float(a[5]),
                    'alt': float(a[6]),
                }
            if (id not in data):
                if isFile:
                    data[id] = {'type': a[12], 'freq': a[13], 'frames': []}
                else:
                    data[id] = {'type': a[1], 'freq': a[2], 'frames': []}
            data[id]['frames'].append(frame)
except serial.SerialException:
    print(f'La seriale {sys.argv[n+1]} non esiste')
    fine = True
except Exception as x:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    print("line "+str(exc_tb.tb_lineno)+": "+str(x), file=sys.stderr)
    sys.stderr.flush()
