import http.server
import os
import re
import socketserver
import logging
import threading
import json

import shutil

import util


def create_handler(config, threads):
    class VideoServerRequestHandler(http.server.BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.config = config
            self.threads = threads
            super().__init__(*args, **kwargs)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header('Access-Control-Allow-Methods', 'GET,PUT,DELETE')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Allow', 'GET,PUT,DELETE')
            self.end_headers()

        def do_PUT(self):
            name = util.escape_name(self.path[1:])
            if not self.headers['Content-Length'] \
                    or not self.headers['Content-Type'] \
                    or not self.headers['Content-Type'].split(';')[0] == 'application/json' \
                    or not len(name):
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            length = self.headers['Content-Length']
            request = json.JSONDecoder().decode(self.rfile.read(int(length)).decode("utf-8"))
            logging.debug('HTTP API PUT: {}'.format(request))
            if 'source' not in request:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            if 'live' not in request:
                request['live'] = True
            if 'rec' not in request:
                request['rec'] = True
            if 'snap' not in request:
                request['snap'] = True
            if 'segment_duration' not in request:
                request['segment_duration'] = None
            config.add_stream({
                'name': name,
                'source': request['source'],
                'live': request['live'],
                'rec': request['rec'],
                'snap': request['snap'],
                'segment_duration': request['segment_duration']
            })
            response = json.JSONEncoder().encode({'success': True})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.end_headers()
            self.wfile.write(bytes(response, 'utf-8'))

        def do_DELETE(self):
            name = util.escape_name(self.path[1:])
            success = self.config.remove_stream(name)

            if name in self.threads:
                self.threads[name].stop()
            files_to_delete = []
            for filename in os.listdir(self.config.get_rec_dir()):
                if re.match('{}_\d+\.mp4'.format(name), filename) or filename == '{}_latest'.format(name):
                    files_to_delete.append(os.path.join(self.config.get_rec_dir(), filename))
            for filename in os.listdir(self.config.get_live_dir()):
                if re.match('{}\d+\.(ts)'.format(name), filename) \
                        or filename == '{}.jpg'.format(name) \
                        or filename == '{}.m3u8'.format(name):
                    files_to_delete.append(os.path.join(self.config.get_live_dir(), filename))
            for filename in files_to_delete:
                logging.info('Removing file "{}" due to stream removal'.format(filename))
                try:
                    os.remove(os.path.join(self.config.get_rec_dir(), filename))
                except FileNotFoundError:
                    pass

            response = json.JSONEncoder().encode({'success': success})

            self.send_response(200 if success else 404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.end_headers()
            self.wfile.write(bytes(response, 'utf-8'))

        def do_GET(self):
            if self.path[1:] == ':free':
                result = shutil.disk_usage(self.config.get_rec_dir()).free
            elif self.path[1:] == ':free_str':
                result = util.filesizeformat(shutil.disk_usage(self.config.get_rec_dir()).free)
            else:
                name = util.escape_name(self.path[1:])
                if len(name):
                    result = config.get_stream(name)
                else:
                    result = config.get_streams()
            response = json.JSONEncoder().encode(result)
            self.send_response(200 if result is not None else 404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.end_headers()
            self.wfile.write(bytes(response, 'utf-8'))

        def version_string(self):
            return 'videoserver'

        def log_message(self, fmt, *args):
            logging.debug('HTTPServer: %s', (fmt % args))
            pass

    return VideoServerRequestHandler


class HttpApi:
    def __init__(self, config, threads):
        self.config = config
        self.threads = threads
        self.port = self.config.get_http_port()
        self.addr = self.config.get_http_addr()
        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = socketserver.TCPServer(('', self.port), create_handler(self.config, self.threads))
        self.running = False

    def start(self):
        logging.debug('HTTP API server stating on port {:d}'.format(self.port))
        thread = threading.Thread(target=self.httpd.serve_forever)
        thread.daemon = True
        thread.start()
        self.running = True

    def stop(self):
        logging.debug('HTTP API server shutting down')
        self.httpd.shutdown()
        self.running = False
