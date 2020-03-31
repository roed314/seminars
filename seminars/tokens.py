from .app import app
from itsdangerous import URLSafeTimedSerializer, URLSafeSerializer

def generate_token(obj, salt):
    serializer = URLSafeSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(obj, salt=salt)

def read_token(token, salt, expiration=86400):
    serializer = URLSafeSerializer(app.config['SECRET_KEY'])
    obj = serializer.loads(
        token,
        salt=salt
    )
    return obj

def generate_timed_token(obj, salt):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(obj, salt=salt)

def read_timed_token(token, salt, expiration=86400):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    obj = serializer.loads(
        token,
        salt=salt,
        max_age=expiration
    )
    return obj
