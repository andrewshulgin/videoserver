import os
import subprocess
import signal
import logging

import util


class FFmpeg:
    def __init__(self, name, source, live=None, rec=None, segment_duration=10, snap=True, log=None):
        self.bin = '/usr/bin/ffmpeg'

        self.name = util.escape_name(name)
        self.source = source
        if live:
            self.live = os.path.realpath(live)
        else:
            self.live = False
        if rec:
            self.rec = os.path.realpath(rec)
        else:
            self.rec = False
        self.segment_duration = segment_duration
        self.snap = snap

        self.cmd = self._construct_cmd()
        self.subprocess = None

        self.logfile = open(log, 'a+') if log else None

    def _construct_cmd(self):
        self.cmd = [
            self.bin, '-y', '-nostats', '-stimeout', '1000000', '-re', '-rtsp_transport', 'tcp', '-i', self.source
        ]
        if self.live:
            hls_file = os.path.join(self.live, '{}.m3u8'.format(self.name))
            self.cmd += ['-an', '-c:v', 'copy', '-hls_flags', 'delete_segments', hls_file]
        if self.rec:
            rec_file_format = os.path.join(self.rec, '{}_%Y%m%d%H%M.mp4'.format(self.name))
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
        ffmpeg_logfile = self.logfile if self.logfile is not None else subprocess.DEVNULL
        self.subprocess = subprocess.Popen(
            self.cmd,
            stdout=ffmpeg_logfile,
            stderr=ffmpeg_logfile,
            stdin=subprocess.DEVNULL
        )

    def stop(self):
        if not self.cmd or not self.subprocess:
            return None
        logging.info('Stopping FFmpeg for {}'.format(self.name))
        try:
            self.subprocess.send_signal(signal.SIGTERM)
            try:
                ret = self.subprocess.wait(10)
            except subprocess.TimeoutExpired:
                logging.warning('Failed to stop FFmpeg for {}, killing'.format(self.name))
                self.subprocess.kill()
                ret = -1
        except ProcessLookupError:
            ret = self.subprocess.poll()
        logging.info('Stopped FFmpeg for {}'.format(self.name))
        if self.logfile:
            self.logfile.flush()
            self.logfile.close()
        return ret

    def status(self):
        if not self.cmd or not self.subprocess:
            return False, None
        return True, self.subprocess.poll()
