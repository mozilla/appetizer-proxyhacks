import re

_end_head_re = re.compile(r'</head\s*>', re.I)


def add_head(req, resp, content):
    body = resp.body
    match = _end_head_re.search(body)
    if not match:
        resp.body = content + body
    else:
        resp.body = resp.body[match.start():] + content + resp.body[:match.start()]
    return resp
