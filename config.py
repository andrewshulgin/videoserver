import configparser
import logging
import os
import shutil
import socket

import util


class FFmpegNotFoundError(Exception):
    def __str__(self):
        return 'FFmpeg binary not found'


class Config:
    def __init__(self):
        self.stream_prefix = 'stream:'
        self.parser = configparser.ConfigParser()
        self.stream_parser = configparser.ConfigParser()
        self.config_dir = os.path.join(os.path.dirname(__file__), 'conf')
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, 'videoserver.ini')
        self.stream_config_file = os.path.join(self.config_dir, 'streams.ini')
        self.parser.read(self.config_file)
        self.stream_parser.read(self.stream_config_file)
        self._init_config()

    def _init_config(self):
        if not self.parser.has_section('general'):
            self.parser.add_section('general')
        if not self.parser.has_option('general', 'ffmpeg_bin'):
            bin_ = shutil.which('ffmpeg')
            if not bin_:
                raise FileNotFoundError('FFmpeg binary not found. Set ffmpeg_bin in the general config section')
            logging.warning('ffmpeg_bin not set, guessed: {}'.format(bin_))
            self.parser.set('general', 'ffmpeg_bin', bin_)
        if not self.parser.has_option('general', 'stop_timeout'):
            self.parser.set('general', 'stop_timeout', '10')
        if not self.parser.has_option('general', 'segment_duration'):
            self.parser.set('general', 'segment_duration', '3600')
        if not self.parser.has_option('general', 'live_dir'):
            dir_ = os.path.join(os.path.dirname(__file__), 'live')
            logging.warning('live_dir not set, falling back to {}'.format(dir_))
            self.parser.set('general', 'live_dir', dir_)
        if not self.parser.has_option('general', 'rec_dir'):
            dir_ = os.path.join(os.path.dirname(__file__), 'rec')
            logging.warning('rec_dir not set, falling back to {}'.format(dir_))
            self.parser.set('general', 'rec_dir', dir_)
        if not self.parser.has_option('general', 'http_addr'):
            logging.warning('http_addr not set, falling back to 127.0.0.1')
            self.parser.set('general', 'http_addr', '127.0.0.1')
        if not self.parser.has_option('general', 'http_port'):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 0))
            port_ = s.getsockname()[1]
            s.close()
            logging.warning('http_port not set, picked {}'.format(port_))
            self.parser.set('general', 'http_port', str(port_))
        if not self.parser.has_option('general', 'rec_keep_hours'):
            self.parser.set('general', 'rec_keep_hours', '12')
        if not self.parser.has_option('general', 'rec_keep_mb'):
            self.parser.set('general', 'rec_keep_mb', '100')
        self.save()

    def _parse_stream(self, section):
        name = section[len(self.stream_prefix):]
        if self.stream_parser.has_option(section, 'source'):
            source = self.stream_parser.get(section, 'source')
        else:
            logging.warning('Stream {} has no source, ignoring'.format(name))
            return None
        live = self.stream_parser.getboolean(section, 'live')
        rec = self.stream_parser.getboolean(section, 'rec')
        snap = self.stream_parser.getboolean(section, 'snap')
        segment_duration = self.get_segment_duration()
        if rec:
            if self.stream_parser.has_option(section, 'segment_duration'):
                segment_duration = self.stream_parser.getint(section, 'segment_duration')
            else:
                segment_duration = self.get_segment_duration()
        return {
            'name': name,
            'source': source,
            'live': live,
            'rec': rec,
            'snap': snap,
            'segment_duration': segment_duration
        }

    def get_ffmpeg_bin(self):
        return self.parser.get('general', 'ffmpeg_bin')

    def get_stop_timeout(self):
        return self.parser.get('general', 'stop_timeout')

    def get_segment_duration(self):
        return self.parser.getint('general', 'segment_duration')

    def get_live_dir(self):
        return self.parser.get('general', 'live_dir')

    def get_rec_dir(self):
        return self.parser.get('general', 'rec_dir')

    def get_http_addr(self):
        return self.parser.get('general', 'http_addr')

    def get_http_port(self):
        return self.parser.getint('general', 'http_port')

    def get_rec_keep_hours(self):
        return self.parser.getint('general', 'rec_keep_hours')

    def get_rec_keep_mb(self):
        return self.parser.getint('general', 'rec_keep_mb')

    def get_streams(self):
        streams = []
        for section in self.stream_parser.sections():
            if section[:len(self.stream_prefix)] == self.stream_prefix:
                streams.append(self._parse_stream(section))
        return streams

    def get_stream(self, name):
        return self._parse_stream('{}{}'.format(self.stream_prefix, util.escape_name(name)))

    def add_stream(self, params):
        if 'name' not in params:
            logging.error('Stream has no name')
            return
        if 'source' not in params:
            logging.error('Stream has no source')
            return
        if 'live' not in params:
            params['live'] = True
        if 'rec' not in params:
            params['rec'] = True
        if 'snap' not in params:
            params['snap'] = True
        if 'segment_duration' not in params:
            params['segment_duration'] = None
        name = util.escape_name(params['name'])
        section = '{}{}'.format(self.stream_prefix, util.escape_name(name))
        self.stream_parser.add_section(section)
        self.stream_parser.set(section, 'source', params['source'])
        self.stream_parser.set(section, 'live', 'true' if params['live'] else 'false')
        self.stream_parser.set(section, 'rec', 'true' if params['rec'] else 'false')
        self.stream_parser.set(section, 'snap', 'true' if params['snap'] else 'false')
        if params['segment_duration'] is not None:
            self.stream_parser.set(section, 'segment_duration', params['segment_duration'])
        self.save_streams()

    def remove_stream(self, name):
        name = util.escape_name(name)
        section = '{}{}'.format(self.stream_prefix, name)
        success = True
        if not self.stream_parser.has_section(section):
            success = False
            logging.error('No such stream: {}'.format(name))
        self.stream_parser.remove_section(section)
        self.save_streams()
        return success

    def save(self):
        with open(self.config_file, 'w') as fp:
            self.parser.write(fp)

    def save_streams(self):
        with open(self.stream_config_file, 'w') as fp:
            self.stream_parser.write(fp)
