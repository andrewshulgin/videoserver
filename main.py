#!/usr/bin/env python3
import datetime
import os
import re
import shutil
import signal
import threading
import time
import logging
import sys

import config
import ffmpeg
import util
import httpapi
import notifiers


def configure_logging():
    logging.root.setLevel(logging.NOTSET)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
    logging.root.addHandler(handler)


class Application:
    def __init__(self):
        self.running = False
        self.config = None
        self.threads = {}
        self.notifiers = []
        self.server = None

    def _send_notification(self, message):
        for notifier in self.notifiers:
            threading.Thread(target=notifier.send, args=[message]).start()

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
        if self.config.get_slack_enabled():
            self.notifiers.append(notifiers.Slack(self.config))
        if self.config.get_smtp_enabled():
            self.notifiers.append(notifiers.SMTP(self.config))
        if self.config.get_telegram_enabled():
            self.notifiers.append(notifiers.Telegram(self.config))
        self._send_notification('Started')
        fs_limit = 99
        fs_limit_counter = 0
        # wait before assuming that ffmpeg is running ok
        ff_limit = self.config.get_ffmpeg_start_timeout() * 100
        ff_limit_counter = 0
        rec_keep_timedelta = datetime.timedelta(seconds=self.config.get_rec_keep_hours())
        failed_streams = []
        while self.running:
            time.sleep(0.01)

            ok = True
            if fs_limit_counter == 0:
                recordings = []
                for filename in os.listdir(self.config.get_rec_dir()):
                    if re.match('[A-z-_\d]+_\d+\.mp4', filename):
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
                while shutil.disk_usage(self.config.get_rec_dir()).free < (self.config.get_keep_free_mb() * 1000000):
                    if not recordings or len(recordings) < 1:
                        logging.critical('Unable to free up the required space')
                        self._send_notification('Unable to free up the required space')
                        ok = False
                        break
                    filename = recordings[0]
                    logging.warning('Free space is less than {:d} MB'.format(self.config.get_keep_free_mb()))
                    logging.warning('Removing record {} due to lack of free space'.format(filename))
                    os.remove(os.path.join(self.config.get_rec_dir(), filename))
                    recordings = []
                    for filename in os.listdir(self.config.get_rec_dir()):
                        if re.match('\w+_\d+\.mp4', filename):
                            recordings.append(filename)
            elif fs_limit_counter > fs_limit:
                fs_limit_counter = 0
            else:
                fs_limit_counter += 1

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
                    self.threads[stream['name']] = ffmpeg.FFmpeg(
                        name, source, live, rec, segment_duration, snap,
                        stop_timeout=self.config.get_ffmpeg_stop_timeout()
                    )

            threads_to_stop = []
            for name, thread in self.threads.items():
                if name not in active_stream_names:
                    threads_to_stop.append(name)
            for name in threads_to_stop:
                self.threads[name].stop()
                if name in failed_streams:
                    failed_streams.remove(name)
                del self.threads[name]

            for stream, thread in self.threads.items():
                started, status = thread.status()
                if not started:
                    logging.info('Starting FFmpeg for {}'.format(stream))
                    thread.start()
                elif status is not None:
                    ff_limit_counter = 0
                    if stream not in failed_streams:
                        logging.warning(
                            'FFmpeg for stream {} exited with status {:d}, restarting'.format(
                                stream, status
                            ))
                        self._send_notification(
                            'FFmpeg for stream {} exited with status {:d}'.format(stream, status))
                        failed_streams.append(stream)
                    thread.start()
                else:
                    if stream in failed_streams:
                        if ff_limit_counter < ff_limit:
                            ff_limit_counter += 1
                        else:
                            logging.info('FFmpeg for stream {} restored'.format(stream))
                            self._send_notification('FFmpeg for stream {} restored'.format(stream))
                            failed_streams.remove(stream)

        logging.info('Shutting down')
        self._send_notification('Shutting down')
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
