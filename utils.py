def serialize_decimals(obj):
    if isinstance(obj, dict):
        return {k: serialize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_decimals(i) for i in obj]
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    return obj
