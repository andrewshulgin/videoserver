import string
import urllib.request


def escape_name(s):
    valid_chars = "-_" + string.ascii_letters + string.digits
    filename = ''.join(c for c in s if c in valid_chars)
    return filename


def filesizeformat(b):
    try:
        b = float(b)
    except (TypeError, ValueError, UnicodeDecodeError):
        return '0 B'

    kb = 1 << 10
    mb = 1 << 20
    gb = 1 << 30
    tb = 1 << 40

    negative = b < 0
    if negative:
        b = -b

    if b < kb:
        value = "{:d} B".format(b)
    elif b < mb:
        value = "{:.2f} KB".format(b / kb)
    elif b < gb:
        value = "{:.2f} MB".format(b / mb)
    elif b < tb:
        value = "{:.2f} GB".format(b / gb)
    else:
        value = "{:.2f} TB".format(b / tb)

    if negative:
        value = "-{}".format(value)
    return value


class TolerantHTTPErrorProcessor(urllib.request.HTTPErrorProcessor):
    def __init__(self):
        super().__init__()

    def http_response(self, req, res):
        return res

    https_response = http_response
