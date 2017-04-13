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
        if not self.parser.has_section('recording'):
            self.parser.add_section('recording')
        if not self.parser.has_section('api'):
            self.parser.add_section('api')
        if not self.parser.has_section('slack'):
            self.parser.add_section('slack')
        if not self.parser.has_section('smtp'):
            self.parser.add_section('smtp')
        if not self.parser.has_section('telegram'):
            self.parser.add_section('telegram')

        if not self.parser.has_option('general', 'ffmpeg_bin'):
            bin_ = shutil.which('ffmpeg')
            if not bin_:
                raise FileNotFoundError('FFmpeg binary not found. Set ffmpeg_bin in the general config section')
            logging.warning('ffmpeg_bin not set, guessed: {}'.format(bin_))
            self.parser.set('general', 'ffmpeg_bin', bin_)
        if not self.parser.has_option('general', 'ffmpeg_start_timeout'):
            self.parser.set('general', 'ffmpeg_start_timeout', '20')
        if not self.parser.has_option('general', 'ffmpeg_stop_timeout'):
            self.parser.set('general', 'ffmpeg_stop_timeout', '10')
        if not self.parser.has_option('general', 'live_dir'):
            dir_ = os.path.join(os.path.dirname(__file__), 'static', 'live')
            logging.warning('live_dir not set, falling back to {}'.format(dir_))
            self.parser.set('general', 'live_dir', dir_)
        if not self.parser.has_option('general', 'rec_dir'):
            dir_ = os.path.join(os.path.dirname(__file__), 'static', 'rec')
            logging.warning('rec_dir not set, falling back to {}'.format(dir_))
            self.parser.set('general', 'rec_dir', dir_)
        if not self.parser.has_option('general', 'keep_free_mb'):
            self.parser.set('general', 'keep_free_mb', '100')

        if not self.parser.has_option('api', 'http_addr'):
            logging.warning('http_addr not set, falling back to 127.0.0.1')
            self.parser.set('api', 'http_addr', '127.0.0.1')
        if not self.parser.has_option('api', 'http_port'):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 0))
            port_ = s.getsockname()[1]
            s.close()
            logging.warning('http_port not set, picked {}'.format(port_))
            self.parser.set('api', 'http_port', str(port_))

        if not self.parser.has_option('recording', 'rec_keep_hours'):
            self.parser.set('recording', 'rec_keep_hours', '12')
        if not self.parser.has_option('recording', 'segment_duration'):
            self.parser.set('recording', 'segment_duration', '3600')

        if not self.parser.has_option('slack', 'enabled'):
            self.parser.set('slack', 'enabled', 'false')
        if not self.parser.has_option('slack', 'webhook_url'):
            self.parser.set('slack', 'webhook_url', 'change_me')
        if not self.parser.has_option('slack', 'channel'):
            self.parser.set('slack', 'channel', '#general')

        if not self.parser.has_option('smtp', 'enabled'):
            self.parser.set('smtp', 'enabled', 'false')
        if not self.parser.has_option('smtp', 'server'):
            self.parser.set('smtp', 'server', 'example.com')
        if not self.parser.has_option('smtp', 'port'):
            self.parser.set('smtp', 'port', '587')
        if not self.parser.has_option('smtp', 'login'):
            self.parser.set('smtp', 'login', 'videoserver@example.com')
        if not self.parser.has_option('smtp', 'password'):
            self.parser.set('smtp', 'password', 'change_me')
        if not self.parser.has_option('smtp', 'from'):
            self.parser.set('smtp', 'from', 'videoserver@example.com')
        if not self.parser.has_option('smtp', 'subject'):
            self.parser.set('smtp', 'subject', 'VideoServer Notification')
        if not self.parser.has_option('smtp', 'recipient'):
            self.parser.set('smtp', 'recipient', 'user@exmaple.com')
        if not self.parser.has_option('smtp', 'security'):
            self.parser.set('smtp', 'security', 'starttls')

        if not self.parser.has_option('telegram', 'enabled'):
            self.parser.set('telegram', 'enabled', 'false')
        if not self.parser.has_option('telegram', 'api_key'):
            self.parser.set('telegram', 'api_key', 'change_me')
        if not self.parser.has_option('telegram', 'chat_id'):
            self.parser.set('telegram', 'chat_id', '@example')
        if not self.parser.has_option('telegram', 'convert_chat_id'):
            self.parser.set('telegram', 'convert_chat_id', 'true')

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

    def get_ffmpeg_start_timeout(self):
        return self.parser.getint('general', 'ffmpeg_start_timeout')

    def get_ffmpeg_stop_timeout(self):
        return self.parser.getint('general', 'ffmpeg_stop_timeout')

    def get_segment_duration(self):
        return self.parser.getint('recording', 'segment_duration')

    def get_live_dir(self):
        return self.parser.get('general', 'live_dir')

    def get_rec_dir(self):
        return self.parser.get('general', 'rec_dir')

    def get_http_addr(self):
        return self.parser.get('api', 'http_addr')

    def get_http_port(self):
        return self.parser.getint('api', 'http_port')

    def get_rec_keep_hours(self):
        return self.parser.getint('recording', 'rec_keep_hours')

    def get_keep_free_mb(self):
        return self.parser.getint('general', 'keep_free_mb')

    def get_slack_enabled(self):
        return self.parser.getboolean('slack', 'enabled')

    def get_slack_webhook_url(self):
        return self.parser.get('slack', 'webhook_url')

    def get_slack_channel(self):
        return self.parser.get('slack', 'channel')

    def get_smtp_enabled(self):
        return self.parser.getboolean('smtp', 'enabled')

    def get_smtp_server(self):
        return self.parser.get('smtp', 'server')

    def get_smtp_port(self):
        return self.parser.getint('smtp', 'port')

    def get_smtp_login(self):
        return self.parser.get('smtp', 'login')

    def get_smtp_password(self):
        return self.parser.get('smtp', 'password')

    def get_smtp_from(self):
        return self.parser.get('smtp', 'from')

    def get_smtp_subject(self):
        return self.parser.get('smtp', 'subject')

    def get_smtp_recipient(self):
        return self.parser.get('smtp', 'recipient')

    def get_smtp_security(self):
        return self.parser.get('smtp', 'security')

    def get_telegram_enabled(self):
        return self.parser.getboolean('telegram', 'enabled')

    def get_telegram_api_key(self):
        return self.parser.get('telegram', 'api_key')

    def get_telegram_chat_id(self):
        return self.parser.get('telegram', 'chat_id')

    def set_telegram_chat_id(self, chat_id):
        self.parser.set('telegram', 'chat_id', str(chat_id))
        self.save()

    def get_telegram_convert_chat_id(self):
        return self.parser.getboolean('telegram', 'convert_chat_id')

    def save(self):
        with open(self.config_file, 'w') as fp:
            self.parser.write(fp)

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

    def save_streams(self):
        with open(self.stream_config_file, 'w') as fp:
            self.stream_parser.write(fp)
