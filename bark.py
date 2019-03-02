import falcon
import shortuuid
import records
import os
from apns2.client import APNsClient
from apns2.payload import Payload, PayloadAlert
from apns2.errors import APNsException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'db.sqlite')
CERT_PATH = os.path.join(BASE_DIR, 'cert-20200229.pem')


def push(category, title, body, device_token, params):
    payload = Payload(PayloadAlert(
        title=title,
        body=body),
        sound='1107', badge=int(params['badge']) if 'badge' in params else 0,
        category=category, mutable_content=True, **params)
    topic = 'me.fin.bark'
    client = APNsClient(CERT_PATH)

    try:
        client.send_notification(device_token, payload, topic)
        return ''
    except APNsException as e:
        return str(e)


class RequireJSON(object):
    def process_request(self, req, resp):
        if not req.client_accepts_json:
            raise falcon.HTTPNotAcceptable(
                'This API only supports responses encoded as JSON.',
                href='https://github.com/billzhong/py-bark')


class PingResource(object):
    def on_get(self, req, resp):
        resp.media = {
            'code': 200,
            'data': {
                'version': '1.0.0'
            },
            'message': 'pong'
        }


class RegisterResource(object):
    def __init__(self, _db):
        self.db = _db

    def on_get(self, req, resp):

        device_token = req.get_param('devicetoken')
        key = shortuuid.uuid()

        if not device_token:
            resp.media = {
                'code': 400,
                'data': None,
                'message': 'Device token can not be empty.',
            }
            resp.status = falcon.HTTP_400
            return

        old_key = req.get_param('key')
        rows = self.db.query('SELECT * FROM devices WHERE key = :key', True, key=old_key)
        if rows:
            self.db.query('UPDATE devices SET token=:token WHERE key = :key', token=device_token, key=old_key)
            key = old_key
        else:
            self.db.query('INSERT INTO devices (token, key) VALUES(:token, :key)', token=device_token, key=key)

        resp.media = {
            'code': 200,
            'data': {
                'key': key
            },
            'message': 'Registration Successful'
        }


class IndexResource(object):
    def __init__(self, _db):
        self.db = _db

    def on_get(self, req, resp, key, **kwargs):
        rows = self.db.query('SELECT * FROM devices WHERE key = :key', True, key=key)

        if not rows:
            resp.media = {
                'code': 400,
                'data': None,
                'message': 'Key is not found, please check again. Key can be obtained from App.',
            }
            resp.status = falcon.HTTP_400
            return

        device_token = rows[0]['token']

        if 'title' in kwargs:
            title = kwargs['title']
        else:
            title = ''

        if title == '':
            title = req.media.get('title')

        if 'body' in kwargs:
            body = kwargs['body']
        else:
            body = ''

        if title == '':
            body = req.media.get('title')

        error = push('myNotificationCategory', title, body, device_token, req.params)

        if error == '':
            resp.media = {
                'code': 200,
                'data': None,
                'message': '',
            }
        else:
            resp.media = {
                'code': 400,
                'data': None,
                'message': error,
            }
            resp.status = falcon.HTTP_400

    def on_post(self, req, resp, key, **kwargs):
        pass


app = falcon.API(middleware=[
    RequireJSON(),
])

if os.path.isfile(DB_PATH):
    first_time = False
else:
    first_time = True
db = records.Database('sqlite:///' + DB_PATH)

if first_time:
    db.query('DROP TABLE IF EXISTS devices')
    db.query('CREATE TABLE devices '
             '(id INTEGER PRIMARY KEY AUTOINCREMENT, token CHAR(32) NOT NULL , key CHAR(22) NOT NULL)')

ping = PingResource()
register = RegisterResource(db)
index = IndexResource(db)

app.add_route('/ping', ping)
app.add_route('/register', register)
app.add_route('/{key}', index)
app.add_route('/{key}/{title}', index)
app.add_route('/{key}/{title}/{body}', index)

if __name__ == '__main__':
    from wsgiref import simple_server

    httpd = simple_server.make_server('0.0.0.0', 8000, app)
    httpd.serve_forever()
