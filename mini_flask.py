
class MultiDict(dict):
    def get(self, key, default=None, type=None):
        val = super().get(key, default)
        if val is None or val == default:
            return default
        if isinstance(val, list):
            val = val[0] if len(val) > 0 else default
        if type is not None:
            try:
                return type(val)
            except (ValueError, TypeError):
                return default
        return val

    def getlist(self, key):
        val = super().get(key, [])
        if isinstance(val, list):
            return val
        return [val] if val is not None else []
# -*- coding: utf-8 -*-
"""
Mini-Flask: A self-contained, lightweight, WSGI-compliant Flask-compatible implementation.
Provides Flask routing, request/response, session management, file uploads, Jinja2 rendering,
context processors, and a full test client without external dependencies beyond standard library + jinja2.
"""
import os, sys, re, json, hmac, hashlib, base64, urllib.parse, mimetypes, io
from datetime import datetime
from collections import defaultdict
import jinja2

_current_app = None

class FileStorage:
    def __init__(self, filename, content, content_type='application/octet-stream'):
        self.filename = filename
        self._content = content
        self.content_type = content_type
        self.stream = io.BytesIO(content) if isinstance(content, bytes) else io.BytesIO(content.encode('utf-8'))

    def save(self, dst):
        if isinstance(dst, (str, os.PathLike)):
            with open(dst, 'wb') as f:
                f.write(self._content if isinstance(self._content, bytes) else self._content.encode('utf-8'))
        else:
            dst.write(self._content if isinstance(self._content, bytes) else self._content.encode('utf-8'))

    def read(self, *args):
        return self.stream.read(*args)

    def seek(self, *args):
        return self.stream.seek(*args)

    def __bool__(self):
        return bool(self.filename)

class Request:
    def __init__(self, environ=None):
        self.environ = environ or {}
        self.method = self.environ.get('REQUEST_METHOD', 'GET').upper()
        self.path = self.environ.get('PATH_INFO', '/')
        self.query_string = self.environ.get('QUERY_STRING', '')
        self.args = MultiDict()
        if self.query_string:
            qs_dict = urllib.parse.parse_qs(self.query_string, keep_blank_values=True)
            self.args = {k: v[0] if len(v) == 1 else v for k, v in qs_dict.items()}
        
        self.form = MultiDict()
        self._raw_files = defaultdict(list)
        self.json = None
        self.cookies = {}
        self.headers = {}
        
        raw_cookies = self.environ.get('HTTP_COOKIE', '')
        if raw_cookies:
            for item in raw_cookies.split(';'):
                if '=' in item:
                    ck, cv = item.strip().split('=', 1)
                    self.cookies[ck.strip()] = urllib.parse.unquote(cv.strip())

        for k, v in self.environ.items():
            if k.startswith('HTTP_'):
                hdr = k[5:].replace('_', '-').title()
                self.headers[hdr] = v

        self._parse_body()

    def get_json(self, silent=True):
        return self.json

    def _parse_body(self):
        content_type = self.environ.get('CONTENT_TYPE', '')
        try:
            content_length = int(self.environ.get('CONTENT_LENGTH', 0))
        except (ValueError, TypeError):
            content_length = 0

        input_stream = self.environ.get('wsgi.input')
        body = b''
        if input_stream and content_length > 0:
            body = input_stream.read(content_length)

        if 'application/json' in content_type:
            try:
                self.json = json.loads(body.decode('utf-8'))
            except Exception:
                self.json = None
        elif 'multipart/form-data' in content_type and 'boundary=' in content_type:
            boundary = content_type.split('boundary=')[-1].strip().strip('"').encode('utf-8')
            parts = body.split(b'--' + boundary)
            for part in parts:
                if not part or part == b'--\r\n' or part == b'--':
                    continue
                if b'\r\n\r\n' in part:
                    header_raw, content = part.split(b'\r\n\r\n', 1)
                    content = content.rstrip(b'\r\n')
                    header_str = header_raw.decode('latin-1', errors='ignore')
                    disp_match = re.search(r'Content-Disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]*)")?', header_str, re.IGNORECASE)
                    if disp_match:
                        field_name = disp_match.group(1)
                        filename = disp_match.group(2)
                        if filename is not None:
                            ctype_match = re.search(r'Content-Type:\s*([^\r\n]+)', header_str, re.IGNORECASE)
                            ctype = ctype_match.group(1).strip() if ctype_match else 'application/octet-stream'
                            fs = FileStorage(filename, content, ctype)
                            self._raw_files[field_name].append(fs)
                        else:
                            val = content.decode('utf-8', errors='replace')
                            self.form[field_name] = val
        elif 'application/x-www-form-urlencoded' in content_type or (self.method == 'POST' and body):
            try:
                decoded = body.decode('utf-8', errors='replace')
                parsed = urllib.parse.parse_qs(decoded, keep_blank_values=True)
                for k, v in parsed.items():
                    self.form[k] = v
            except Exception:
                pass

class _FilesProxy:
    def __init__(self, req):
        self.req = req
    def get(self, key, default=None):
        fl = self.req._raw_files.get(key, [])
        return fl[0] if fl else default
    def getlist(self, key):
        return self.req._raw_files.get(key, [])
    def __contains__(self, key):
        return key in self.req._raw_files

class Response:
    def __init__(self, response=b'', status=200, headers=None, mimetype='text/html'):
        self.status_code = status
        self.headers = headers or {}
        self.mimetype = mimetype
        if isinstance(response, str):
            self.data = response.encode('utf-8')
        elif isinstance(response, bytes):
            self.data = response
        else:
            self.data = b''.join(x.encode('utf-8') if isinstance(x, str) else x for x in response)
        
        if 'Content-Type' not in self.headers:
            charset = '; charset=utf-8' if 'text' in mimetype or 'json' in mimetype else ''
            self.headers['Content-Type'] = f'{mimetype}{charset}'

    def set_cookie(self, key, value, max_age=None, path='/', httponly=True, samesite='Lax'):
        val = urllib.parse.quote(str(value))
        cookie_parts = [f'{key}={val}', f'Path={path}']
        if max_age is not None:
            cookie_parts.append(f'Max-Age={max_age}')
        if httponly:
            cookie_parts.append('HttpOnly')
        if samesite:
            cookie_parts.append(f'SameSite={samesite}')
        self.headers['Set-Cookie'] = '; '.join(cookie_parts)

    def delete_cookie(self, key, path='/'):
        self.headers['Set-Cookie'] = f'{key}=; Path={path}; Max-Age=0; HttpOnly'

class LocalProxy:
    def __init__(self, getter):
        self.__dict__['_getter'] = getter
    def _obj(self):
        return self._getter()
    def __getattr__(self, name):
        return getattr(self._obj(), name)
    def __setattr__(self, name, value):
        setattr(self._obj(), name, value)
    def __getitem__(self, item):
        return self._obj()[item]
    def __setitem__(self, item, value):
        self._obj()[item] = value
    def __delitem__(self, item):
        del self._obj()[item]
    def __contains__(self, item):
        return item in self._obj()
    def get(self, *args, **kwargs):
        return self._obj().get(*args, **kwargs)
    def pop(self, *args, **kwargs):
        return self._obj().pop(*args, **kwargs)
    def clear(self):
        return self._obj().clear()
    def update(self, *args, **kwargs):
        return self._obj().update(*args, **kwargs)
    def keys(self):
        return self._obj().keys()
    def values(self):
        return self._obj().values()
    def items(self):
        return self._obj().items()

import threading
_current_context = threading.local()

def _get_current_request():
    req = getattr(_current_context, 'request', None)
    if req is None:
        req = Request()
        _current_context.request = req
    req.files_proxy = _FilesProxy(req)
    req.files = req.files_proxy
    return req

def _get_current_session():
    sess = getattr(_current_context, 'session', None)
    if sess is None:
        sess = {}
        _current_context.session = sess
    return sess

request = LocalProxy(_get_current_request)
session = LocalProxy(_get_current_session)

class HTTPException(Exception):
    def __init__(self, code, description=""):
        super().__init__(description)
        self.code = code
        self.description = description

def abort(code, description=""):
    raise HTTPException(code, description)

def redirect(location, code=302):
    res = Response(status=code)
    res.headers['Location'] = location
    return res

def jsonify(*args, **kwargs):
    data = args[0] if args else kwargs
    res = Response(json.dumps(data, ensure_ascii=False), status=200, mimetype='application/json')
    return res

def send_file(filename_or_fp, mimetype=None, as_attachment=False, download_name=None):
    if isinstance(filename_or_fp, (str, os.PathLike)):
        p = str(filename_or_fp)
        if not os.path.isfile(p):
            abort(404, "File not found")
        with open(p, 'rb') as f:
            data = f.read()
        fname = download_name or os.path.basename(p)
        mime = mimetype or mimetypes.guess_type(p)[0] or 'application/octet-stream'
    else:
        data = filename_or_fp.read()
        fname = download_name or 'file'
        mime = mimetype or 'application/octet-stream'
        
    headers = {}
    if as_attachment:
        enc_fname = urllib.parse.quote(fname)
        headers['Content-Disposition'] = f'attachment; filename="{fname}"; filename*=UTF-8\'\'{enc_fname}'
    return Response(data, status=200, headers=headers, mimetype=mime)

def flash(message, category='message'):
    sess = _get_current_session()
    flashes = sess.setdefault('_flashes', [])
    flashes.append((category, message))

def get_flashed_messages(with_categories=False):
    sess = _get_current_session()
    flashes = sess.pop('_flashes', [])
    if with_categories:
        return flashes
    return [msg for _, msg in flashes]

def url_for(endpoint, **values):
    global _current_app
    if _current_app:
        return _current_app.url_for(endpoint, **values)
    if endpoint == 'static':
        return f"/static/{values.get('filename', '')}"
    return f"/{endpoint}"

def render_template(template_name, **context):
    global _current_app
    ctx = {}
    if _current_app:
        for proc in _current_app._context_processors:
            ctx.update(proc())
        ctx.update(context)
        tmpl = _current_app.jinja_env.get_template(template_name)
        return tmpl.render(**ctx)
    else:
        env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
        return env.get_template(template_name).render(**context)

def render_template_string(source, **context):
    global _current_app
    ctx = {}
    if _current_app:
        for proc in _current_app._context_processors:
            ctx.update(proc())
    ctx.update(context)
    env = jinja2.Environment(autoescape=jinja2.select_autoescape(['html', 'xml']))
    env.globals.update({
        'url_for': url_for,
        'get_flashed_messages': get_flashed_messages,
        'session': session,
        'request': request
    })
    return env.from_string(source).render(**ctx)

class Flask:
    def __init__(self, import_name, static_folder='static', template_folder='templates'):
        global _current_app
        _current_app = self
        self.import_name = import_name
        self.static_folder = static_folder
        self.template_folder = template_folder
        self.secret_key = 'mini-flask-default-secret-key-3746'
        self.config = {'MAX_CONTENT_LENGTH': 100 * 1024 * 1024}
        self.routes = []
        self.endpoint_map = {}
        self.view_functions = {}
        self.error_handlers = {}
        self._context_processors = []
        self.before_request_funcs = []

        template_path = os.path.join(os.path.dirname(__file__), template_folder)
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path) if os.path.isdir(template_path) else jinja2.FileSystemLoader(template_folder),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        self.jinja_env.globals.update({
            'url_for': self.url_for,
            'get_flashed_messages': get_flashed_messages,
            'session': session,
            'request': request,
            'now': lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    def context_processor(self, f):
        self._context_processors.append(f)
        return f

    def before_request(self, f):
        self.before_request_funcs.append(f)
        return f

    def route(self, rule, methods=None, endpoint=None):
        methods = [m.upper() for m in (methods or ['GET'])]
        def decorator(f):
            ep = endpoint or f.__name__
            self.add_url_rule(rule, ep, f, methods=methods)
            return f
        return decorator

    def get(self, rule, endpoint=None):
        return self.route(rule, methods=['GET'], endpoint=endpoint)

    def post(self, rule, endpoint=None):
        return self.route(rule, methods=['POST'], endpoint=endpoint)

    def add_url_rule(self, rule, endpoint, view_func, methods=None):
        methods = methods or ['GET']
        regex_pattern = '^'
        var_names = []
        parts = rule.split('/')
        new_parts = []
        for p in parts:
            if p.startswith('<') and p.endswith('>'):
                raw = p[1:-1]
                if ':' in raw:
                    converter, name = raw.split(':', 1)
                else:
                    converter, name = 'string', raw
                var_names.append((name, converter))
                if converter == 'int':
                    new_parts.append(r'(?P<' + name + r'>\d+)')
                else:
                    new_parts.append(r'(?P<' + name + r'>[^/]+)')
            else:
                new_parts.append(re.escape(p))
        regex_pattern += '/'.join(new_parts)
        if not rule.endswith('/') and rule != '/':
            regex_pattern += r'/?$'
        else:
            regex_pattern += r'$'
        
        compiled_regex = re.compile(regex_pattern)
        if endpoint in self.view_functions and self.view_functions[endpoint] is not view_func:
            raise AssertionError(f"View function mapping is overwriting an existing endpoint function: {endpoint}")
        self.view_functions[endpoint] = view_func
        self.routes.append((compiled_regex, methods, endpoint, view_func, var_names, rule))
        self.endpoint_map[endpoint] = (rule, var_names)

    def errorhandler(self, code):
        def decorator(f):
            self.error_handlers[code] = f
            return f
        return decorator

    def url_for(self, endpoint, **values):
        if endpoint == 'static':
            filename = values.get('filename', '')
            return f'/{self.static_folder}/{filename}'
        if endpoint not in self.endpoint_map:
            return f'/{endpoint}'
        rule, var_names = self.endpoint_map[endpoint]
        result = rule
        used = set()
        for name, converter in var_names:
            if name in values:
                result = result.replace(f'<{converter}:{name}>' if f'<{converter}:{name}>' in result else f'<{name}>', str(values[name]))
                used.add(name)
        remaining = {k: v for k, v in values.items() if k not in used}
        if remaining:
            result += '?' + urllib.parse.urlencode(remaining)
        return result

    def _sign_session(self, sess_data):
        raw = json.dumps(sess_data).encode('utf-8')
        sig = hmac.new(self.secret_key.encode('utf-8'), raw, hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(raw).decode('ascii') + '.' + sig

    def _unsign_session(self, cookie_val):
        try:
            if not cookie_val or '.' not in cookie_val:
                return {}
            b64_raw, sig = cookie_val.split('.', 1)
            raw = base64.urlsafe_b64decode(b64_raw.encode('ascii'))
            expected_sig = hmac.new(self.secret_key.encode('utf-8'), raw, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig):
                return json.loads(raw.decode('utf-8'))
        except Exception:
            pass
        return {}

    def wsgi_app(self, environ, start_response):
        path = environ.get('PATH_INFO', '/')
        method = environ.get('REQUEST_METHOD', 'GET').upper()
        
        # Static files handling
        static_prefix = f'/{self.static_folder}/'
        if path.startswith(static_prefix):
            rel_path = path[len(static_prefix):]
            base_dir = os.path.dirname(__file__)
            file_path = os.path.join(base_dir, self.static_folder, rel_path)
            if not os.path.isfile(file_path):
                file_path = os.path.join(self.static_folder, rel_path)

            if os.path.isfile(file_path):
                mime = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
                with open(file_path, 'rb') as f:
                    content = f.read()
                status_str = "200 OK"
                response_headers = [('Content-Type', mime), ('Content-Length', str(len(content)))]
                start_response(status_str, response_headers)
                return [content]
            else:
                start_response("404 Not Found", [('Content-Type', 'text/plain')])
                return [b"Not Found"]

        req = Request(environ)
        sess = self._unsign_session(req.cookies.get('session', ''))
        _current_context.request = req
        _current_context.session = sess

        matched_route = None
        kwargs = {}
        for pattern, methods, ep, func, var_names, rule in self.routes:
            m = pattern.match(path)
            if m:
                if method not in methods:
                    continue
                matched_route = func
                raw_kwargs = m.groupdict()
                for name, converter in var_names:
                    val = raw_kwargs.get(name)
                    if converter == 'int':
                        kwargs[name] = int(val)
                    else:
                        kwargs[name] = urllib.parse.unquote(val)
                break

        res = None
        try:
            for b_func in self.before_request_funcs:
                b_res = b_func()
                if b_res is not None:
                    if isinstance(b_res, Response):
                        res = b_res
                    elif isinstance(b_res, tuple):
                        body = b_res[0]
                        status = b_res[1] if len(b_res) > 1 else 200
                        hdrs = b_res[2] if len(b_res) > 2 else {}
                        if isinstance(body, Response):
                            res = body
                            res.status_code = status
                        else:
                            res = Response(body, status=status, headers=hdrs)
                    else:
                        res = Response(b_res)
                    break

            if res is not None:
                pass
            elif not matched_route:
                if 404 in self.error_handlers:
                    res = self.error_handlers[404](None)
                else:
                    res = Response("<h1>404 Not Found</h1>", status=404, mimetype='text/html')
            else:
                result = matched_route(**kwargs)
                if isinstance(result, Response):
                    res = result
                elif isinstance(result, tuple):
                    body = result[0]
                    status = result[1] if len(result) > 1 else 200
                    hdrs = result[2] if len(result) > 2 else {}
                    if isinstance(body, Response):
                        res = body
                        res.status_code = status
                    else:
                        res = Response(body, status=status, headers=hdrs)
                else:
                    res = Response(result)
        except HTTPException as e:
            if e.code in self.error_handlers:
                res = self.error_handlers[e.code](e)
            else:
                res = Response(f"<h1>Error {e.code}</h1><p>{e.description}</p>", status=e.code, mimetype='text/html')
        except Exception as e:
            import traceback
            traceback.print_exc()
            if 500 in self.error_handlers:
                res = self.error_handlers[500](e)
            else:
                res = Response(f"<h1>500 Internal Server Error</h1><pre>{e}</pre>", status=500, mimetype='text/html')

        if not isinstance(res, Response):
            res = Response(res)

        new_sess = getattr(_current_context, 'session', {})
        res.set_cookie('session', self._sign_session(new_sess), path='/')

        status_str = f"{res.status_code} " + {200: "OK", 302: "Found", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 500: "Internal Server Error"}.get(res.status_code, "OK")
        hdrs = list(res.headers.items())
        hdrs.append(('Content-Length', str(len(res.data))))
        start_response(status_str, hdrs)
        return [res.data]

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def test_client(self):
        return TestClient(self)

    def run(self, host='127.0.0.1', port=8765, debug=False, **kwargs):
        from wsgiref.simple_server import make_server
        print(f" * Serving Mini-Flask app '{self.import_name}' on http://{host}:{port}")
        server = make_server(host, port, self.wsgi_app)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

class TestResponse:
    def __init__(self, status_code, headers, data):
        self.status_code = status_code
        self.headers = dict(headers)
        self.data = data
    @property
    def text(self):
        return self.data.decode('utf-8', errors='replace')
    def get_json(self):
        return json.loads(self.text)

class TestClient:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def __init__(self, app):
        self.app = app
        self.cookie_jar = {}

    def _request(self, method, path, query_string=None, data=None, json_data=None, headers=None, content_type=None):
        environ = {
            'REQUEST_METHOD': method.upper(),
            'PATH_INFO': path.split('?')[0],
            'QUERY_STRING': query_string or (path.split('?')[1] if '?' in path else ''),
            'wsgi.input': io.BytesIO(b''),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '8765',
        }
        
        cookie_header = '; '.join(f'{k}={v}' for k, v in self.cookie_jar.items())
        if cookie_header:
            environ['HTTP_COOKIE'] = cookie_header

        body_bytes = b''
        ctype = content_type
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode('utf-8')
            ctype = 'application/json'
        elif isinstance(data, dict):
            has_files = any(isinstance(v, (FileStorage, tuple)) for v in data.values())
            if has_files:
                boundary = '----MiniFlaskBoundary' + hashlib.md5(os.urandom(16)).hexdigest()
                ctype = f'multipart/form-data; boundary={boundary}'
                b_parts = []
                for k, v in data.items():
                    if isinstance(v, FileStorage):
                        b_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{v.filename}"\r\nContent-Type: {v.content_type}\r\n\r\n'.encode('utf-8') + v._content + b'\r\n')
                    elif isinstance(v, tuple):
                        if isinstance(v[0], str):
                            fname, fcontent = v[0], v[1]
                        else:
                            fcontent, fname = v[0], v[1]
                        if hasattr(fcontent, 'read'):
                            fcontent = fcontent.read()
                        b_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode('utf-8') + (fcontent if isinstance(fcontent, bytes) else fcontent.encode('utf-8')) + b'\r\n')
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, FileStorage):
                                b_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{item.filename}"\r\nContent-Type: {item.content_type}\r\n\r\n'.encode('utf-8') + item._content + b'\r\n')
                            else:
                                b_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{item}\r\n'.encode('utf-8'))
                    else:
                        b_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
                b_parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
                body_bytes = b''.join(b_parts)
            else:
                body_bytes = urllib.parse.urlencode(data, doseq=True).encode('utf-8')
                ctype = 'application/x-www-form-urlencoded'
        elif isinstance(data, (str, bytes)):
            body_bytes = data if isinstance(data, bytes) else data.encode('utf-8')

        if ctype:
            environ['CONTENT_TYPE'] = ctype
        environ['CONTENT_LENGTH'] = str(len(body_bytes))
        environ['wsgi.input'] = io.BytesIO(body_bytes)

        if headers:
            for k, v in headers.items():
                environ['HTTP_' + k.upper().replace('-', '_')] = str(v)

        status_box = []
        headers_box = []
        def start_response(status, response_headers):
            status_box.append(int(status.split()[0]))
            headers_box.extend(response_headers)

        output = self.app.wsgi_app(environ, start_response)
        data_out = b''.join(output)

        for hk, hv in headers_box:
            if hk.lower() == 'set-cookie':
                parts = hv.split(';')
                if parts and '=' in parts[0]:
                    ck, cv = parts[0].strip().split('=', 1)
                    if 'Max-Age=0' in hv:
                        self.cookie_jar.pop(ck, None)
                    else:
                        self.cookie_jar[ck] = cv

        return TestResponse(status_box[0], headers_box, data_out)

    def get(self, path, **kwargs):
        return self._request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self._request('POST', path, **kwargs)
    def delete(self, path, **kwargs):
        return self._request('DELETE', path, **kwargs)

    def delete(self, path, **kwargs):
        return self._request('DELETE', path, **kwargs)
