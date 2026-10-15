
from django.db import transaction

from planning_measurements.models import Goal, MeasurementItem


def importar_items():
    metas = Goal.objects.filter(deleted_at__isnull=True)

    nombres = sorted(
        set(
            metas.exclude(item__isnull=True)
            .exclude(item__exact="")
            .values_list("item", flat=True)
        )
    )

    with transaction.atomic():
        for numero, nombre in enumerate(nombres, start=1):
            unidades = set(
                metas.filter(item=nombre)
                .exclude(unit__isnull=True)
                .exclude(unit__exact="")
                .values_list("unit", flat=True)
            )

            unidad = (
                next(iter(unidades))
                if len(unidades) == 1
                else ""
            )

            existente = MeasurementItem.objects.filter(
                name=nombre
            ).first()

            if existente:
                print(f"YA EXISTE: {existente.name}")
                continue

            codigo_base = f"ITEM-{numero:03d}"
            codigo = codigo_base
            sufijo = 1

            while MeasurementItem.objects.filter(code=codigo).exists():
                codigo = f"{codigo_base}-{sufijo}"
                sufijo += 1

            item = MeasurementItem.objects.create(
                code=codigo,
                name=nombre,
                description="",
                unit=unidad,
                is_active=True,
            )

            print(
                f"CREADO: {item.code} - {item.name} "
                f"| Unidad: {item.unit or 'Pendiente'}"
            )

    print("Importación terminada.")


importar_items()
