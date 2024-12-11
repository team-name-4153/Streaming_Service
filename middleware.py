# middleware.py

from flask import request, redirect, make_response, session
from functools import wraps
import requests
import os
from jose import jwt, jwk
from jose.utils import base64url_decode
import time
from flask_socketio import SocketIO, disconnect, emit



# Middleware configuration
AUTH_SERVICE_BASE_URL = os.getenv('AUTH_SERVICE_BASE_URL')
COGNITO_DOMAIN = os.getenv('COGNITO_DOMAIN')
COGNITO_CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')
COGNITO_CLIENT_SECRET = os.getenv('COGNITO_CLIENT_SECRET')
TOKEN_URL = f"{COGNITO_DOMAIN}/oauth2/token"
JWKS_URL = f"{COGNITO_DOMAIN}/.well-known/jwks.json"


def validate_jwt_token(token):
    try:
        jwks_response = requests.get(JWKS_URL).json()
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        key = next(k for k in jwks_response["keys"] if k["kid"] == kid)
        public_key = jwk.construct(key)

        # Verify the token
        message, encoded_signature = token.rsplit(".", 1)
        decoded_signature = base64url_decode(encoded_signature.encode())
        if not public_key.verify(message.encode(), decoded_signature):
            return False, None

        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=COGNITO_CLIENT_ID,
        )
        if claims.get("exp", 0) < int(time.time()):
            return False, None

        return True, claims
    except Exception as e:
        print(f"Token validation error: {e}")
        return False, None


def token_required_socket(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        from app import socketio
        # Access tokens sent during connection are stored in flask's request context
        access_token = request.args.get('access_token')
        refresh_token = request.args.get('refresh_token')

        if access_token:
            valid, claims = validate_jwt_token(access_token)
            if valid:
                # Attach user info to the socket session
                socketio.server.environ[socketio.sid]['user_info'] = {
                    "user_id": claims.get("sub"),
                    "email": claims.get("email"),
                    "photo_url": claims.get("picture"),
                }
                return f(*args, **kwargs)

        if refresh_token:
            try:
                token_payload = {
                    "grant_type": "refresh_token",
                    "client_id": COGNITO_CLIENT_ID,
                    "client_secret": COGNITO_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                }
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                response = requests.post(TOKEN_URL, data=token_payload, headers=headers)
                new_tokens = response.json()

                if "error" in new_tokens:
                    raise Exception(new_tokens["error_description"])

                # Emit event to update tokens on the client side
                emit('update_tokens', {
                    "access_token": new_tokens.get("access_token"),
                    # Uncomment if you handle refresh tokens via sockets
                    # "refresh_token": new_tokens.get("refresh_token"),
                    # "id_token": new_tokens.get("id_token"),
                }, to=request.sid)

                # Validate the new access token
                valid, claims = validate_jwt_token(new_tokens.get("access_token"))
                if valid:
                    socketio.server.environ[socketio.sid]['user_info'] = {
                        "user_id": claims.get("sub"),
                        "email": claims.get("email"),
                        "photo_url": claims.get("picture"),
                    }
                    return f(*args, **kwargs)
                else:
                    raise Exception("Invalid new access token.")

            except Exception as e:
                print(f"Token refresh error: {e}")

        # If authentication fails, disconnect the socket
        print(f"{AUTH_SERVICE_BASE_URL}/login?redirect_after_login=your_redirect_url")
        disconnect()
        return

    return wrapped