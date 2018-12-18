#!/usr/bin/env python3
import datetime
import logging
import os
import re
import shutil
import signal
import threading
import time

import config
import ffmpeg
import httpapi
import notifiers
import util


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

    def _send_notification(self, message, stream=None, status=None):
        for notifier in self.notifiers:
            threading.Thread(target=notifier.send, args=[message, stream, status]).start()

    def _find_recordings(self):
        recordings = []
        for filename in os.listdir(self.config.get_rec_dir()):
            if re.match(r'^[A-z-_\d]+_\d+\.mp4$', filename):
                recordings.append(filename)
        return sorted(recordings)

    def _remove_stale_latest_files(self):
        recordings = self._find_recordings()
        for filename in os.listdir(self.config.get_rec_dir()):
            if re.match(r'^[A-z-_\d]+_latest$', filename):
                remove = False
                with open(os.path.join(self.config.get_rec_dir(), filename)) as f:
                    rec_filename = f.readline().strip()
                    if rec_filename not in recordings:
                        remove = True
                if remove:
                    logging.info('Removing stale q{}'.format(filename))
                    try:
                        os.remove(os.path.join(self.config.get_rec_dir(), filename))
                    except FileNotFoundError:
                        pass

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
        if self.config.get_http_get_enabled():
            self.notifiers.append(notifiers.HttpGet(self.config))
        if self.config.get_slack_enabled():
            self.notifiers.append(notifiers.Slack(self.config))
        if self.config.get_smtp_enabled():
            self.notifiers.append(notifiers.SMTP(self.config))
        if self.config.get_telegram_enabled():
            self.notifiers.append(notifiers.Telegram(self.config))
        self._send_notification('Started')
        fs_check_tick_limit = 99
        fs_limit_check_ticks = 0
        # wait before assuming that ffmpeg is running ok
        ff_success_cnt = self.config.get_ffmpeg_start_timeout() * 100
        ff_running_cnt = {}
        rec_keep_timedelta = datetime.timedelta(hours=self.config.get_rec_keep_hours())
        failed_streams = {}
        while self.running:
            time.sleep(0.01)

            ok = True
            if fs_limit_check_ticks == 0:
                recordings = self._find_recordings()
                for filename in recordings:
                    stream_name, datetime_str = str(filename.rsplit('.', 1)[0]).rsplit('_', 1)
                    datetime_ = datetime.datetime.strptime(datetime_str, '%Y%m%d%H%M')
                    if datetime.datetime.now() - datetime_ > rec_keep_timedelta:
                        logging.info('Removing record "{}" due to expiry of {:d} hours'.format(
                            filename, self.config.get_rec_keep_hours()
                        ))
                        try:
                            os.remove(os.path.join(self.config.get_rec_dir(), filename))
                        except FileNotFoundError:
                            pass
                        recordings.remove(filename)
                while shutil.disk_usage(self.config.get_rec_dir()).free < (self.config.get_keep_free_mb() * 1000000):
                    if not recordings or len(recordings) < 1:
                        logging.critical('Unable to free up the required space')
                        self._send_notification('Unable to free up the required space')
                        ok = False
                        break
                    filename = recordings[0]
                    logging.warning('Free space is less than {:d} MB'.format(self.config.get_keep_free_mb()))
                    logging.warning('Removing record {} due to lack of free space'.format(filename))
                    try:
                        os.remove(os.path.join(self.config.get_rec_dir(), filename))
                    except FileNotFoundError:
                        pass
                    recordings = self._find_recordings()
                self._remove_stale_latest_files()
            elif fs_limit_check_ticks > fs_check_tick_limit:
                fs_limit_check_ticks = 0
            else:
                fs_limit_check_ticks += 1

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
                    del failed_streams[name]
                del self.threads[name]

            for stream, thread in self.threads.items():
                started, status = thread.status()
                if not started:
                    logging.info('Starting FFmpeg for {}'.format(stream))
                    thread.start()
                # failed
                elif status is not None:
                    if stream in ff_running_cnt:
                        del ff_running_cnt[stream]
                    if stream in failed_streams:
                        if failed_streams[stream] >= self.config.get_stream_down_timeout():
                            self._send_notification('Stream {} failed'.format(stream), stream, False)
                            failed_streams[stream] = -1
                        elif failed_streams[stream] is not -1:
                            failed_streams[stream] += 1
                    else:
                        logging.warning(
                            'FFmpeg for stream {} exited with status {:d}, restarting'.format(stream, status)
                        )
                        failed_streams[stream] = 0
                    thread.start()
                # running
                else:
                    if stream not in ff_running_cnt:
                        ff_running_cnt[stream] = 0
                    else:
                        if -1 < ff_running_cnt[stream] < ff_success_cnt:
                            ff_running_cnt[stream] += 1
                        else:
                            if stream in failed_streams:
                                logging.info('FFmpeg for stream {} restored'.format(stream))
                                if failed_streams[stream] == -1:
                                    self._send_notification('Stream {} restored'.format(stream), stream, True)
                                del failed_streams[stream]
                            elif ff_running_cnt[stream] is not -1:
                                logging.info('FFmpeg for stream {} started successfully'.format(stream))
                                self._send_notification(None, stream, True)
                                ff_running_cnt[stream] = -1

        logging.info('Shutting down')
        self._send_notification('Shutting down')
        self.server.stop()
        for _, thread in self.threads.items():
            thread.stop()
        return 0

    def reload(self):
        logging.info('Reloading configuration files')
        self.config.reload()
        self.config.reload_streams()

    def stop(self):
        self.running = False


if __name__ == '__main__':
    configure_logging()
    try:
        app = Application()
        signal.signal(signal.SIGINT, lambda signum, frame: app.stop())
        signal.signal(signal.SIGTERM, lambda signum, frame: app.stop())
        signal.signal(signal.SIGHUP, lambda signum, frame: app.reload())
        exit(app.run())
    except Exception as e:
        logging.critical(e or e.__class__.__name__)
        raise
