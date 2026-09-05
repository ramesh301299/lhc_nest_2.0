# -*- coding: utf-8 -*-
import re
from odoo import models


class LhcInrMixin(models.AbstractModel):
    """Adds an ``inr()`` helper so QWeb print templates render amounts with
    Indian digit grouping (e.g. ₹1,84,500) exactly like the Web mockup."""
    _name = 'lhc.inr.mixin'
    _description = 'LHC INR formatting helper'

    def inr(self, value):
        try:
            value = float(value or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        neg = value < 0
        s = '%.0f' % abs(value)
        if len(s) > 3:
            last3, rest = s[-3:], s[:-3]
            rest = re.sub(r'(\d)(?=(\d\d)+$)', r'\1,', rest)
            s = rest + ',' + last3
        return ('- ₹' if neg else '₹') + s
