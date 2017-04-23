import logging
import urllib.error
import urllib.parse
import urllib.request

import util
from notifier import *


class HttpGet(Notifier):
    def send(self, message, stream=None, status=None):
        if stream is None or status is None:
            return
        params = {
            'stream': stream,
            'status': 1 if status else 0,
            # 'message': message
        }
        print('{}?{}'.format(self.config.get_http_get_url(), urllib.parse.urlencode(params)))
        request = urllib.request.Request('{}?{}'.format(
            self.config.get_http_get_url(),
            urllib.parse.urlencode(params))
        )
        opener = urllib.request.build_opener(util.TolerantHTTPErrorProcessor)
        try:
            response = opener.open(request, timeout=4).read().decode('utf-8').replace('\n', '')
        except urllib.error as e:
            response = str(e)
        if response == self.config.get_http_get_success_response():
            logging.info('Sent HTTP GET notification successfully')
        else:
            logging.error('Failed to send HTTP GET notification: {}'.format(response))
