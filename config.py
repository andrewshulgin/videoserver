import configparser
import logging
import os
import shutil
import socket

import util

DEFAULTS = {
    'general': {
        'ffmpeg_start_timeout': '20',
        'ffmpeg_stop_timeout': '10',
        'stream_down_timeout': '60',
        'keep_free_mb': '100'
    },
    'recording': {
        'rec_keep_hours': '12',
        'segment_duration': '3600'
    },
    'api': {},
    'http_get': {
        'enabled': 'false',
        'url': 'http://example.com/notify',
        'success_response': 'ok'
    },
    'slack': {
        'enabled': 'false',
        'webhook_url': 'change_me',
        'channel': '#general'
    },
    'smtp': {
        'enabled': 'false',
        'server': 'example.com',
        'port': '587',
        'login': 'videoserver@example.com',
        'password': 'change_me',
        'from': 'videoserver@example.com',
        'subject': 'VideoServer Notification',
        'recipient': 'user@exmaple.com',
        'security': 'starttls'
    },
    'telegram': {
        'enabled': 'false',
        'api_key': 'change_me',
        'chat_id': '@example',
        'convert_chat_id': 'true'
    }
}


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
        for section, items in DEFAULTS.items():
            if not self.parser.has_section(section):
                self.parser.add_section(section)
                for key, value in items.items():
                    self.parser.set(section, key, value)

        if not self.parser.has_option('general', 'ffmpeg_bin'):
            bin_ = shutil.which('ffmpeg')
            if not bin_:
                raise FileNotFoundError('FFmpeg binary not found. Set ffmpeg_bin in the general config section')
            logging.warning('ffmpeg_bin not set, guessed: {}'.format(bin_))
            self.parser.set('general', 'ffmpeg_bin', bin_)
        if not self.parser.has_option('general', 'live_dir'):
            dir_ = os.path.join(os.path.dirname(__file__), 'static', 'live')
            logging.warning('live_dir not set, falling back to {}'.format(dir_))
            self.parser.set('general', 'live_dir', dir_)
        if not self.parser.has_option('general', 'rec_dir'):
            dir_ = os.path.join(os.path.dirname(__file__), 'static', 'rec')
            logging.warning('rec_dir not set, falling back to {}'.format(dir_))
            self.parser.set('general', 'rec_dir', dir_)

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

    def get_stream_down_timeout(self):
        return self.parser.getint('general', 'stream_down_timeout')

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

    def get_http_get_enabled(self):
        return self.parser.getboolean('http_get', 'enabled')

    def get_http_get_url(self):
        return self.parser.get('http_get', 'url')

    def get_http_get_success_response(self):
        return self.parser.get('http_get', 'success_response')

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

    def reload(self):
        self.parser.read(self.config_file)

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
        name = util.escape_name(params['name'])
        section = '{}{}'.format(self.stream_prefix, util.escape_name(name))
        self.stream_parser.add_section(section)
        self.stream_parser.set(section, 'source', params['source'])
        self.stream_parser.set(section, 'live', 'true' if params.get('live', True) else 'false')
        self.stream_parser.set(section, 'rec', 'true' if params.get('rec', True) else 'false')
        self.stream_parser.set(section, 'snap', 'true' if params.get('snap', True) else 'false')
        if params.get('segment_duration', None) is not None:
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

    def reload_streams(self):
        self.stream_parser.read(self.stream_config_file)
