# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Send existing LHC users to the Dashboard instead of the Apps grid."""
    from .models.res_users import set_lhc_home_action
    set_lhc_home_action(env)
