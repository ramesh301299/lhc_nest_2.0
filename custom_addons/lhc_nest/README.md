# lhc_nest — LHC NEST Base

The foundation every other LHC NEST addon depends on. It holds only what more
than one of them needs, so the business addons never have to depend on each
other.

## What it owns

| Thing | Why it lives here |
|---|---|
| `group_lhc_admin`, `group_lhc_accountant` | Menu security in six addons is written against these two names. |
| `lhc.billing.entity` | The single source of truth for GST applicability — read by leasing, money and reports. |
| `lhc.company.mixin` | One `company_id` definition, so one record-rule pattern scopes every LHC model. |
| `lhc.inr.mixin` | `inr()` for QWeb, so ₹1,84,500 groups the Indian way in every print template. |
| `menu_lhc_root` + five group headers | Each header holds leaves from more than one addon, so it cannot move down into one. |
| `/lhc/data/*` JSON endpoints | `mobile_rest_api` calls them, so the web and Flutter apps cannot disagree about a figure. |

## Layout

```
lhc_nest/
├── __manifest__.py
├── README.md
├── controllers/
│   └── main.py                  # /lhc/data/* — reused by mobile_rest_api
├── data/
│   └── billing_entity_data.xml  # the four lessor entities (noupdate="1")
├── models/
│   ├── billing_entity.py        # lhc.billing.entity + calculate_billing()
│   ├── company_mixin.py         # lhc.company.mixin
│   ├── report_mixin.py          # lhc.inr.mixin
│   └── res_users.py             # _lhc_role() / _lhc_is_user()
├── security/
│   ├── lhc_groups.xml           # roles + category      (noupdate="0")
│   ├── ir.model.access.csv      # ACL grants
│   └── lhc_security_rules.xml   # record rules          (noupdate="0")
├── static/
│   ├── description/icon.png
│   └── src/app/index.html       # legacy SPA mockup served at /lhc
├── tests/
│   ├── test_install.py          # the names other addons import
│   └── test_security.py         # the access matrix
└── views/
    ├── billing_entity_views.xml
    └── menus.xml                # root + the five group headers
```

## Two rules worth not breaking

**GST comes from the entity, and only from the entity.** Never derive it from a
bank account, unit, property or tenant. Every place that needs a GST figure
calls `calculate_billing()` in `models/billing_entity.py` rather than computing
×18% locally, so there is one number and one place to change the rate.

**Maintenance recovery is never GST-marked-up.** It is added to the total after
the tax, outside the taxable base. `calculate_billing()` already does this;
adding it to `rent_amount` before the call is the way to get it wrong.

## Security file convention

`lhc_groups.xml` and `lhc_security_rules.xml` are both `noupdate="0"`, unlike
every other data file in the suite. A role or a rule is the security model, not
an administrator preference, so a correction to one has to reach databases that
already installed the old version. A deployment that genuinely needs a rule
loosened should carry its own module doing so, where the change is reviewable.

XML ids are deliberately unprefixed (`group_lhc_admin`, not
`lhc_nest_group_lhc_admin`): they are already recorded that way in installed
databases, and renaming them would orphan every ACL, rule and menu that
references them.

## Demo data

Each business addon carries a `demo/<module>_demo.xml`, wired through the
`demo` key of its manifest. Together they seed one worked example of the whole
system: two properties (one of them an independent villa, so the auto-unit rule
runs), four units in the four occupancy states, three tenants including a GST
company, four leases covering draft / active / renewed / notice, receipts on
both the GST and non-GST paths, a partial payment, a wrong-bank receipt, the
building-level split engine, a vacate settlement, documents, remittances and
withdrawals.

**Odoo will not load them into a database that was created without demo data.**
`Node.should_have_demo()` requires the module's demo flag *and* the same flag on
every ancestor module, so `base`, `mail` and `web` have to carry it too:

```python
env['ir.module.module'].sudo().search([('state', '=', 'installed')]).write({'demo': True})
```

That is the same write Odoo's own *Load demo data* setting performs. It does not
by itself create Odoo's stock demo records — a module's demo files load only
when that module is upgraded, and upgrading an LHC addon does not upgrade
`base`. Run `-u base` or `-u all` on such a database and the stock demo data
*will* appear, which is the one thing to know before enabling this on a
database that matters.

The flag is self-sustaining afterwards: `load_module_graph` writes the result of
`load_demo` back to `ir_module_module.demo`, but only for modules it is actually
upgrading, so the ancestors keep theirs.

## Tests

```bash
docker exec lovelyhomenest_dev-web odoo -d lovely_homes_nest \
    --test-enable --test-tags /lhc_nest --stop-after-init
```
