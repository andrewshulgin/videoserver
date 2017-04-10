#!/usr/bin/env python3
import datetime
import os
import re
import shutil
import signal
import time
import logging
import sys

import config
import ffmpeg
import util
import httpapi


def configure_logging():
    logging.root.setLevel(logging.NOTSET)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%d-%m %H:%M:%S'))
    logging.root.addHandler(handler)


class Application:
    def __init__(self):
        self.running = False
        self.config = None
        self.threads = {}
        self.server = None

    def run(self):
        logging.info('Starting')
        self.config = config.Config()
        self.server = httpapi.HttpApi(self.config, self.threads)
        logging.info('Using FFmpeg binary: {}'.format(self.config.get_ffmpeg_bin()))
        os.makedirs(os.path.realpath(self.config.get_live_dir()), exist_ok=True)
        os.makedirs(os.path.realpath(self.config.get_rec_dir()), exist_ok=True)
        logging.info('Free space: {}'.format(util.filesizeformat(shutil.disk_usage(self.config.get_rec_dir()).free)))
        self.running = True
        self.server.start()
        count = 0
        rec_keep_timedelta = datetime.timedelta(hours=self.config.get_rec_keep_hours())
        while self.running:
            time.sleep(0.01)

            ok = True
            if count == 0:
                recordings = []
                for filename in os.listdir(self.config.get_rec_dir()):
                    if re.match('\w+_\d+\.mp4', filename):
                        recordings.append(filename)
                recordings.sort()
                for filename in recordings:
                    stream_name, datetime_str = str(filename.split('.', 1)[0]).split('_', 1)
                    datetime_ = datetime.datetime.strptime(datetime_str, '%Y%m%d%H%M')
                    if datetime.datetime.now() - datetime_ > rec_keep_timedelta:
                        logging.info('Removing record "{}" due to expiry of {:d} hours'.format(
                            filename, self.config.get_rec_keep_hours()
                        ))
                        os.remove(os.path.join(self.config.get_rec_dir(), filename))
                while shutil.disk_usage(self.config.get_rec_dir()).free < (self.config.get_rec_keep_mb() * 1000000):
                    if not recordings or len(recordings) < 1:
                        logging.critical('Unable to free up the required space')
                        ok = False
                        break
                    filename = recordings[0]
                    logging.warning('Free space is less than {:d} MB'.format(self.config.get_rec_keep_mb()))
                    logging.warning('Removing record {} due to lack of free space'.format(filename))
                    os.remove(os.path.join(self.config.get_rec_dir(), filename))
                    recordings = []
                    for filename in os.listdir(self.config.get_rec_dir()):
                        if re.match('\w+_\d+\.mp4', filename):
                            recordings.append(filename)
            elif count > 99:
                count = 0
            else:
                count += 1

            if not ok:
                break

            active_stream_names = []
            for stream in self.config.get_streams():
                active_stream_names.append(stream['name'])
                if stream['name'] not in self.threads:
                    name = stream['name']
                    source = stream['source']
                    live = None
                    rec = None
                    snap = None
                    segment_duration = self.config.get_segment_duration()
                    if stream['live']:
                        live = self.config.get_live_dir()
                    if stream['rec']:
                        rec = self.config.get_rec_dir()
                    if 'snap' in stream and stream['snap'] is not None:
                        snap = stream['snap']
                    self.threads[stream['name']] = ffmpeg.FFmpeg(name, source, live, rec, segment_duration, snap)
                    self.threads[stream['name']].start()

            threads_to_stop = []
            for name, thread in self.threads.items():
                if name not in active_stream_names:
                    threads_to_stop.append(name)
            for name in threads_to_stop:
                self.threads[name].stop()
                del self.threads[name]

            for stream, thread in self.threads.items():
                status = thread.status()
                if status is None:
                    thread.start()
                elif status is not True:
                    logging.info('FFmpeg for stream {} exited with status {}, restarting in 1 second'.format(
                        stream, status
                    ))
                    time.sleep(1)
                    thread.start()
        logging.info('Shutting down')
        self.server.stop()
        for _, thread in self.threads.items():
            thread.stop()
        return 0

    def stop(self, *_):
        self.running = False


if __name__ == '__main__':
    configure_logging()
    if len(sys.argv) > 1 and sys.argv[1] == '--debug':
        app = Application()
        signal.signal(signal.SIGINT, app.stop)
        signal.signal(signal.SIGTERM, app.stop)
        exit(app.run())
    else:
        try:
            app = Application()
            signal.signal(signal.SIGINT, app.stop)
            signal.signal(signal.SIGTERM, app.stop)
            exit(app.run())
        except Exception as e:
            logging.critical(e or e.__class__.__name__)
