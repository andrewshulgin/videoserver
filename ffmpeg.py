import os
import subprocess
import signal
import logging
import sys

import util


class FFmpeg:
    def __init__(
            self, name, source, ffmpeg_bin='/usr/bin/ffmpeg',
            live=None, rec=None, snap=True,
            segment_duration=10, stop_timeout=10,
            date_fmt='%Y%m%d%H%M%S', debug_output=False,
    ):
        self.bin = ffmpeg_bin

        self.name = util.escape_name(name)
        self.source = source
        if live:
            self.live = os.path.realpath(live)
        else:
            self.live = None
        if rec:
            self.rec = os.path.realpath(rec)
        else:
            self.rec = None
        self.segment_duration = segment_duration
        self.snap = snap
        self.stop_timeout = stop_timeout
        self.date_fmt = date_fmt

        self.cmd = self._construct_cmd()
        self.subprocess = None

        self.debug_output = debug_output

    def _construct_cmd(self):
        self.cmd = [self.bin, '-y', '-timeout', '1000000', '-re', '-rtsp_transport', 'tcp', '-i', self.source]
        if self.live:
            hls_file = os.path.join(self.live, '{}.m3u8'.format(self.name))
            self.cmd += ['-an', '-c:v', 'copy', '-hls_flags', 'delete_segments', hls_file]
        if self.rec:
            rec_file_format = os.path.join(self.rec, '{}_{}.mp4'.format(self.name, self.date_fmt))
            latest_file = os.path.join(self.rec, '{}_latest'.format(self.name))
            self.cmd += [
                '-an', '-c:v', 'copy', '-f', 'segment', '-segment_format_options', 'movflags=faststart',
                '-segment_time', '{:d}'.format(self.segment_duration), '-segment_atclocktime', '1',
                '-segment_list_size', '1', '-segment_list_type', 'flat', '-segment_list', latest_file,
                '-strftime', '1', '-reset_timestamps', '1', rec_file_format
            ]
        if self.snap:
            snap_file = os.path.join(self.live, '{}.jpg'.format(self.name))
            self.cmd += [
                '-an', '-vf', "select='eq(pict_type,PICT_TYPE_I)'", '-vsync', 'vfr', '-q:v', '28', '-update', '1',
                snap_file
            ]
        return self.cmd

    def start(self):
        if not self.cmd:
            return None
        logging.debug('FFmpeg command: %s', subprocess.list2cmdline(self.cmd))
        self.subprocess = subprocess.Popen(
            self.cmd,
            stdout=sys.stderr if self.debug_output else subprocess.DEVNULL,
            stderr=sys.stderr if self.debug_output else subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        self.subprocess.poll()

    def stop(self):
        if not self.cmd or not self.subprocess:
            return None
        logging.info('Stopping FFmpeg for %s', self.name)
        try:
            self.subprocess.send_signal(signal.SIGTERM)
            try:
                ret = self.subprocess.wait(self.stop_timeout)
            except subprocess.TimeoutExpired:
                logging.warning('Failed to stop FFmpeg for %s, killing', self.name)
                self.subprocess.kill()
                ret = -9
        except ProcessLookupError:
            ret = self.subprocess.poll()
        logging.info('Stopped FFmpeg for %s', self.name)
        return ret

    def status(self):
        if not self.cmd or not self.subprocess:
            return False, None
        return True, self.subprocess.poll()
