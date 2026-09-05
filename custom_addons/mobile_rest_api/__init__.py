# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Generate the JWT signing secret once, at install time.

    Doing this here rather than lazily on the first request avoids two HTTP
    workers racing to create *different* secrets, which would silently
    invalidate each other's tokens. The secret is stored in
    ``ir.config_parameter`` and is never returned by any endpoint.
    """
    env['mobile.access.token']._get_secret()
