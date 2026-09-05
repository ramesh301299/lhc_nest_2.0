# -*- coding: utf-8 -*-
# report_mixin and company_mixin first: billing_entity inherits both, so the
# abstract models have to be in the registry before it is declared.
from . import report_mixin
from . import company_mixin
from . import billing_entity
from . import res_users
