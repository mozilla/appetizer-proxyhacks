from webob.dec import wsgify
from webob import exc
from webob import Response
from lxml import html
from wsgiproxy.exactproxy import proxy_exact_request
from pyquery import PyQuery
from paste.fileapp import FileApp
from paste.translogger import TransLogger
import urllib
import posixpath
import os
import re

def norm_path(req):
    path_info = req.path_info
    path_info = posixpath.normpath(path_info)
    if req.path_info.endswith('/') and not path_info.endswith('/'):
        path_info += '/'
    req.path_info = path_info

class Application(object):

    def __init__(self, site_path):
        self.site_path = site_path
        self.sites = {}

    @wsgify
    def __call__(self, req):
        norm_path(req)
        if req.path_info == '/.gitpull':
            return self.gitpull(req)
        host = req.host.split(':')[0]
        if host.endswith('.localhost'):
            host = host[:-len('.localhost')]
        dir = os.path.join(self.site_path, urllib.quote(host, ''))
        if not os.path.exists(dir):
            raise exc.HTTPNotFound('No site registered for domain %s (in %s)'
                                   % (host, dir))
        if dir not in self.sites:
            self.sites[dir] = Site(dir)
        return self.sites[dir]

    def gitpull(self, req):
        import subprocess
        proc = subprocess.Popen(
            ['git', 'pull', 'origin', 'master'],
            cwd=self.site_path)
        # Forget all the old sites; all is new again!
        self.sites = {}
        return Response('ok')

class Site(object):
    def __init__(self, path):
        self.path = path
        self.dyn_registry = []
        self.config = {}
        execfile(os.path.join(path, 'config.py'), self.config)
        self.config.setdefault('host_aliases', [])
        if os.path.exists(os.path.join(path, 'apps.py')):
            ns = {}
            ns['register'] = self.register
            execfile(os.path.join(path, 'apps.py'), ns)
        if os.path.exists(os.path.join(path, 'rewriter.py')):
            ns = {}
            execfile(os.path.join(path, 'rewriter.py'), ns)
            self.rewriter = ns['rewriter']
        else:
            self.rewriter = None
        self.proxyer = TransLogger(proxy_exact_request)

    def register(self, **kw):
        def decorator(func):
            self.dyn_registry.append((
                Matcher(**kw), func))
            return func
        return decorator

    @wsgify
    def __call__(self, req):
        file_app = self.find_file(req)
        if file_app:
            return file_app
        dyn_app = self.find_dyn(req)
        if dyn_app:
            return dyn_app
        resp = self.proxy_req(req)
        resp = self.rewrite_response(req, resp)
        return resp

    def proxy_req(self, req):
        old_host = req.host
        new_host = self.config['host']
        req.host = new_host
        req.environ['SERVER_NAME'] = new_host
        req.environ['SERVER_PORT'] = '80'
        print 'Proxying to %s' % req.url
        resp = req.get_response(self.proxyer)
        resp = self.rewrite_links(req, resp, new_host, old_host)
        return resp

    def rewrite_links(self, req, resp, old_host, new_host):
        repl_hosts = [old_host] + self.config['host_aliases']
        for repl_host in repl_hosts:
            repl_host_re = re.compile(re.escape(repl_host), re.I)
            for name, value in resp.headers.items():
                if name.lower() == 'set-cookie':
                    set_new_host = new_host.split(':')[0]
                else:
                    set_new_host = new_host
                if repl_host_re.search(value):
                    value = repl_host_re.sub(set_new_host, value)
                    print 'Reset %s: %r->%r' % (
                        name, resp.headers[name], value)
                    resp.headers[name] = value
            types = ['xml', 'json', 'html', 'css']
            rewrite_body = any(t in (resp.content_type or '').lower()
                               for t in types)
            if rewrite_body:
                resp.body = repl_host_re.sub(new_host, resp.body)
        return resp

    def find_file(self, req):
        path = os.path.join(self.path, 'static', req.path_info.lstrip('/'))
        path = os.path.normpath(path)
        assert path.startswith(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, 'index.html')
        if os.path.exists(path):
            return FileApp(path)
        path = path + '.headers'
        if os.path.exists(path):
            return ExplicitFile(path)
        return None

    def find_dyn(self, req):
        for matcher, app in self.dyn_registry:
            if matcher(req):
                resp = app(req)
                return resp
        return None

    def rewrite_response(self, req, resp):
        if self.rewriter:
            new_resp = self.rewriter(req, resp)
            if new_resp:
                return new_resp
        return resp


class ExplicitFile(object):

    def __init__(self, path):
        self.path = path

    @wsgify
    def __call__(self, req):
        fp = open(self.path, 'rb')
        resp = Response()
        resp.content_type = 'application/octet-stream'
        resp.last_modified = os.path.getmtime(self.path)
        for line in fp:
            line = line.strip()
            if not line:
                break
            name, value = line.split(':')
            resp.headers[name] = value.strip()
        resp.body = fp.read()
        return resp

class Matcher(object):
    def __init__(self, func=None, path=None, regex=None):
        self.func = func
        self.path = path
        self.regex = regex
    def __call__(self, req):
        if self.func:
            return self.func(req)
        if self.path:
            return req.path_info.startswith(self.path)
        if self.regex:
            return re.search(req.path_info, self.regex)
        return None

