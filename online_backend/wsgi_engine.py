# -*- coding: utf-8 -*-
"""
Standalone Lightweight WSGI API Engine for Examora AI Online Cloud Backend
Zero coupling with local mini_flask or local templates.
Pure REST API supporting JSON/Form parsing, routing, and test client.
"""
import re, json, urllib.parse, io

class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get('REQUEST_METHOD', 'GET').upper()
        self.path = environ.get('PATH_INFO', '/')
        self.headers = {}
        for k, v in environ.items():
            if k.startswith('HTTP_'):
                hdr = k[5:].replace('_', '-').title()
                self.headers[hdr] = v
            elif k in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                hdr = k.replace('_', '-').title()
                self.headers[hdr] = v

        self.remote_addr = environ.get('REMOTE_ADDR', '127.0.0.1')
        self._body = None
        self._json = None
        self._form = None
        self._parse_body()

    def _parse_body(self):
        try:
            length = int(self.environ.get('CONTENT_LENGTH', 0))
        except (ValueError, TypeError):
            length = 0
        input_stream = self.environ.get('wsgi.input')
        self._body = input_stream.read(length) if (input_stream and length > 0) else b''

        ctype = self.headers.get('Content-Type', '')
        if 'application/json' in ctype and self._body:
            try:
                self._json = json.loads(self._body.decode('utf-8'))
            except Exception:
                self._json = {}
        elif 'application/x-www-form-urlencoded' in ctype and self._body:
            parsed = urllib.parse.parse_qs(self._body.decode('utf-8'))
            self._form = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    @property
    def json(self):
        return self._json

    @property
    def form(self):
        return self._form or {}

class Response:
    def __init__(self, body="", status=200, headers=None, mimetype="text/plain"):
        self.status_code = status
        self.mimetype = mimetype
        self.headers = headers or {}
        if 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = f"{mimetype}; charset=utf-8"

        if isinstance(body, (dict, list)):
            self.body_bytes = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.headers['Content-Type'] = 'application/json; charset=utf-8'
        elif isinstance(body, str):
            self.body_bytes = body.encode('utf-8')
        elif isinstance(body, bytes):
            self.body_bytes = body
        else:
            self.body_bytes = str(body).encode('utf-8')

        self.headers['Content-Length'] = str(len(self.body_bytes))

    def __call__(self, environ, start_response):
        status_line = f"{self.status_code} " + {
            200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized",
            403: "Forbidden", 404: "Not Found", 429: "Too Many Requests", 500: "Internal Server Error"
        }.get(self.status_code, "OK")
        start_response(status_line, list(self.headers.items()))
        return [self.body_bytes]

def jsonify(data):
    return Response(data, status=200, mimetype='application/json')

class OnlineApp:
    def __init__(self, name=None):
        self.routes = []

    def route(self, rule, methods=None):
        methods = [m.upper() for m in (methods or ['GET'])]
        # Convert Flask-style <param> to regex
        pattern_str = '^'
        var_names = []
        for part in rule.split('/'):
            if not part:
                continue
            if part.startswith('<') and part.endswith('>'):
                raw = part[1:-1]
                conv, name = ('string', raw) if ':' not in raw else raw.split(':', 1)
                var_names.append((name, conv))
                if conv == 'path':
                    pattern_str += r'/(?P<' + name + r'>.+)'
                else:
                    pattern_str += r'/(?P<' + name + r'>[^/]+)'
            else:
                pattern_str += '/' + re.escape(part)
        pattern_str += '/?$'
        regex = re.compile(pattern_str)

        def decorator(f):
            self.routes.append((regex, methods, f, var_names, rule))
            return f
        return decorator

    def get(self, rule):
        return self.route(rule, methods=['GET'])

    def post(self, rule):
        return self.route(rule, methods=['POST'])

    def wsgi_app(self, environ, start_response):
        path = environ.get('PATH_INFO', '/')
        method = environ.get('REQUEST_METHOD', 'GET').upper()
        req = Request(environ)

        import sys; we = sys.modules.get(__name__)
        if we:
            we.current_request = req

        if method == 'OPTIONS':
            res = Response('', status=200)
            from security import apply_cors_headers
            apply_cors_headers(res, req.headers.get('Origin', ''))
            return res(environ, start_response)

        matched_func = None
        kwargs = {}
        for pattern, methods, func, var_names, rule in self.routes:
            m = pattern.match(path)
            if m:
                if method not in methods:
                    continue
                matched_func = func
                for name, conv in var_names:
                    val = m.group(name)
                    kwargs[name] = int(val) if conv == 'int' else urllib.parse.unquote(val)
                break

        if not matched_func:
            res = Response(json.dumps({'ok': False, 'error': 'Not Found'}), status=404, mimetype='application/json')
            return res(environ, start_response)

        try:
            result = matched_func(**kwargs)
            if isinstance(result, Response):
                return result(environ, start_response)
            elif isinstance(result, tuple):
                body, status = result[0], result[1]
                res = Response(body, status=status)
                return res(environ, start_response)
            else:
                res = Response(result)
                return res(environ, start_response)
        except Exception as e:
            res = Response(json.dumps({'ok': False, 'error': f'Internal Server Error: {e}'}), status=500, mimetype='application/json')
            return res(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def run(self, host='0.0.0.0', port=8080):
        from wsgiref.simple_server import make_server
        print(f"Examora Online Cloud Backend running on {host}:{port}")
        httpd = make_server(host, port, self)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

    def test_client(self):
        return OnlineTestClient(self)

current_request = None
class RequestProxy:
    def __getattr__(self, item):
        import sys; we = sys.modules.get(__name__)
        if we.current_request is None:
            raise RuntimeError("Working outside of request context")
        return getattr(we.current_request, item)

request = RequestProxy()

class OnlineTestClient:
    def __init__(self, app):
        self.app = app

    def _request(self, method, path, json_data=None, data=None, headers=None):
        body_bytes = b''
        content_type = 'text/plain'
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode('utf-8')
            content_type = 'application/json'
        elif isinstance(data, dict):
            body_bytes = urllib.parse.urlencode(data).encode('utf-8')
            content_type = 'application/x-www-form-urlencoded'

        environ = {
            'REQUEST_METHOD': method.upper(),
            'PATH_INFO': path.split('?')[0],
            'QUERY_STRING': path.split('?')[1] if '?' in path else '',
            'CONTENT_TYPE': content_type,
            'CONTENT_LENGTH': str(len(body_bytes)),
            'wsgi.input': io.BytesIO(body_bytes),
            'REMOTE_ADDR': '127.0.0.1'
        }
        if headers:
            for k, v in headers.items():
                environ['HTTP_' + k.upper().replace('-', '_')] = str(v)

        status_box = []
        headers_box = []
        def start_response(status, response_headers):
            status_box.append(int(status.split()[0]))
            headers_box.extend(response_headers)

        output = self.app.wsgi_app(environ, start_response)
        body = b''.join(output)
        return OnlineTestResponse(status_box[0] if status_box else 200, headers_box, body)

    def get(self, path, **kwargs): return self._request('GET', path, **kwargs)
    def post(self, path, **kwargs): return self._request('POST', path, **kwargs)
    def delete(self, path, **kwargs): return self._request('DELETE', path, **kwargs)

class OnlineTestResponse:
    def __init__(self, status_code, headers, data):
        self.status_code = status_code
        self.headers = dict(headers)
        self.data = data
        self.text = data.decode('utf-8')
    def get_json(self):
        return json.loads(self.text)
