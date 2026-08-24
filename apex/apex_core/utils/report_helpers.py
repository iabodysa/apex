# Copyright (c) 2026, afmcoltd



def date_range_condition(filters, field, from_key="from_date", to_key="to_date"):
    from_value = filters.get(from_key)
    to_value = filters.get(to_key)
    if from_value and to_value:
        return ["between", [from_value, to_value]]
    if from_value:
        return [">=", from_value]
    if to_value:
        return ["<=", to_value]
    return None
