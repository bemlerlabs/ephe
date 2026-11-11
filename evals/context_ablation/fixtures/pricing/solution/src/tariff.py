BASIS_POINTS = {"saturday": 1500, "sunday": 500}


def weekend_surcharge(cents: int, weekday: str) -> int:
    rate = BASIS_POINTS.get(weekday, 0)
    return (cents * (10_000 + rate) + 9_999) // 10_000
