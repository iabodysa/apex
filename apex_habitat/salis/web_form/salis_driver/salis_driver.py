# Copyright (c) 2026, AFMCO and contributors
def get_context(context):
    # login_required + apply_document_permissions gate the create natively:
    # only a logged-in user whose role has Salis Driver "create" may submit.
    context.no_cache = 1
