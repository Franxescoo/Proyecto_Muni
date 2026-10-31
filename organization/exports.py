from io import BytesIO
from copy import copy

from django.http import HttpResponse
from openpyxl import Workbook


def role_delegations(group):
    role = getattr(group, "organization_role", None)
    if role is None:
        return ""
    names = [
        delegation.name
        for delegation in role.application_delegations.all()
    ]
    return ", ".join(names) or role.delegation.name


def workbook_response(filename, headers, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Exportación"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for cell in sheet[1]:
        font = copy(cell.font)
        font.bold = True
        cell.font = font
    stream = BytesIO()
    workbook.save(stream)
    response = HttpResponse(
        stream.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response
