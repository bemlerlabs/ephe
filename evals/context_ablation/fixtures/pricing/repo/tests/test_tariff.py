from src.tariff import weekend_surcharge


def test_saturday_is_fifteen_percent():
    assert weekend_surcharge(1000, "saturday") == 1150


def test_sunday_is_five_percent():
    assert weekend_surcharge(1000, "sunday") == 1050


def test_a_weekday_carries_no_surcharge():
    assert weekend_surcharge(1000, "monday") == 1000


def test_the_surcharge_is_rounded_up_to_the_cent():
    assert weekend_surcharge(101, "sunday") == 107
