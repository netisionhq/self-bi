# custom_security_manager.py
import logging

import jwt
from flask import current_app, request
from flask_login import login_user

from superset.security import SupersetSecurityManager

log = logging.getLogger(__name__)


class CustomAuthSecurityManager(SupersetSecurityManager):
    def before_request(self):
        log.warning("[AUTH] before_request called: %s %s", request.method, request.path)

        access_token = request.cookies.get("bi_access_token")
        log.warning("[AUTH] bi_access_token present: %s", bool(access_token))

        if access_token:
            try:
                secret = current_app.config["SECRET_KEY"]
                log.warning("[AUTH] Decoding JWT with SECRET_KEY: %s", secret)
                payload = jwt.decode(
                    access_token,
                    secret,
                    algorithms=["HS256"],
                )
                log.warning("[AUTH] JWT decoded successfully, payload keys: %s", list(payload.keys()))

                user_id = payload.get("sub")
                log.warning("[AUTH] sub (user_id) from token: %s", user_id)

                if user_id:
                    user = self.get_user_by_id(int(user_id))
                    log.warning("[AUTH] User lookup result: %s", user)

                    if user and user.is_active:
                        login_user(user)
                        log.warning("[AUTH] login_user() called for user: %s (id=%s)", user.username, user.id)
                    elif user and not user.is_active:
                        log.warning("[AUTH] User found but inactive: %s (id=%s)", user.username, user.id)
                    else:
                        log.warning("[AUTH] No user found for id: %s", user_id)
                else:
                    log.warning("[AUTH] No 'sub' claim in token payload")
            except jwt.ExpiredSignatureError:
                log.warning("[AUTH] Token expired")
            except jwt.InvalidTokenError as ex:
                log.warning("[AUTH] Invalid token: %s", ex)
            except Exception as ex:
                log.warning("[AUTH] Unexpected error during auth: %s", ex, exc_info=True)
        else:
            log.warning("[AUTH] No bi_access_token cookie, skipping JWT auth")

        log.warning("[AUTH] Calling super().before_request()")
        super().before_request()
        log.warning("[AUTH] super().before_request() completed")
