import json
import logging
import urllib.error
import urllib.request

import util
from notifier import *


class Telegram(Notifier):
    def send(self, message, stream=None, status=None):
        if message is None:
            return
        url = 'https://api.telegram.org/bot{}/sendMessage'.format(self.config.get_telegram_api_key())
        params = {'chat_id': self.config.get_telegram_chat_id(), 'text': message}
        request = urllib.request.Request(
            url=url,
            data=json.dumps(params).encode('utf-8'),
            headers={'content-type': 'application/json'},
        )
        opener = urllib.request.build_opener(util.TolerantHTTPErrorProcessor)
        try:
            response = json.loads(opener.open(request, timeout=4).read().decode('utf-8'))
        except urllib.error as e:
            logging.error('Failed to send Telegram message: {}'.format(str(e)))
            return
        if response['ok']:
            logging.info('Sent Telegram message successfully')
            if not self.config.get_telegram_chat_id().lstrip('-').isnumeric() \
                    and self.config.get_telegram_convert_chat_id():
                self.config.set_telegram_chat_id(response['result']['chat']['id'])
        else:
            logging.error('Failed to send Telegram message: {}'.format(response['description']))
