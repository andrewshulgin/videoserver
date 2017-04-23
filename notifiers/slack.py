import json
import logging
import urllib.error
import urllib.request

import util
from notifier import *


class Slack(Notifier):
    def send(self, message, stream=None, status=None):
        if message is None:
            return
        params = {'channel': self.config.get_slack_channel(), 'text': message}
        request = urllib.request.Request(
            url=self.config.get_slack_webhook_url(),
            data=json.dumps(params).encode('utf-8'),
            headers={'content-type': 'application/json'}
        )
        opener = urllib.request.build_opener(util.TolerantHTTPErrorProcessor)
        try:
            response = opener.open(request, timeout=4).read().decode('utf-8')
        except urllib.error as e:
            response = str(e)
        if response == 'ok':
            logging.info('Sent Slack message successfully')
        else:
            logging.error('Failed to send Slack message: {}'.format(response))
