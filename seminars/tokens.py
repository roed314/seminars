from .app import app
from itsdangerous import URLSafeTimedSerializer, URLSafeSerializer


def generate_token(obj, salt, key=None):
    if not key:
        key = app.config["SECRET_KEY"]
    serializer = URLSafeSerializer(key)
    return serializer.dumps(obj, salt=salt)


def read_token(token, salt, expiration=86400, key=None):
    if not key:
        key = app.config["SECRET_KEY"]
    serializer = URLSafeSerializer(key)
    obj = serializer.loads(token, salt=salt)
    return obj


def generate_timed_token(obj, salt, key=None):
    if not key:
        key = app.config["SECRET_KEY"]
    serializer = URLSafeTimedSerializer(key)
    return serializer.dumps(obj, salt=salt)


def read_timed_token(token, salt, expiration=86400, key=None):
    if not key:
        key = app.config["SECRET_KEY"]
    serializer = URLSafeTimedSerializer(key)
    obj = serializer.loads(token, salt=salt, max_age=expiration)
    return obj
