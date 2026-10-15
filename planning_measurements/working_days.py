
from datetime import timedelta

import holidays


def calculate_computable_days(start_date, end_date):
    """
    Calcula días computables de un período en Chile.

    Incluye:
        - Lunes a viernes.

    Excluye:
        - Sábados.
        - Domingos.
        - Feriados de Chile.

    Incluye ambas fechas del rango.
    """

    if start_date is None or end_date is None:
        return 0

    if end_date < start_date:
        raise ValueError(
            "La fecha de término no puede ser anterior al inicio."
        )

    chilean_holidays = holidays.country_holidays(
        "CL",
        years=range(
            start_date.year,
            end_date.year + 1
        )
    )

    computable_days = 0
    current_date = start_date

    while current_date <= end_date:

        is_weekday = current_date.weekday() < 5

        is_holiday = current_date in chilean_holidays

        if is_weekday and not is_holiday:
            computable_days += 1

        current_date += timedelta(days=1)

    return computable_days
