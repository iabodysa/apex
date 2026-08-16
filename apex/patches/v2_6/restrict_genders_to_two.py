# Copyright (c) 2026, afmcoltd
"""Remove the Genders Apex does not offer from a site that already ran the setup wizard.

`after_install` covers a new site. A site installed earlier carries all seven Genders that
`frappe.desk.page.setup_wizard.install_fixtures.update_genders` created, and a patch is the
one mechanism that reaches it exactly once.
"""

from apex.setup import restrict_genders


def execute():
    restrict_genders()
