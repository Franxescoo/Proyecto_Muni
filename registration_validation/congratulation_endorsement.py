"""Respaldo formal de felicitaciones: identidad del delegado y documento.

No confundir el campo seleccionable «verificador» con la identidad de la
cuenta que realmente inicia sesión y entrega el respaldo formal.
"""

from django.core.exceptions import ValidationError
from django.utils import timezone


def supporting_document_exists(evidence):
    """Utiliza los formatos de respaldo que ya admite Evidencias en el SGR."""
    if (getattr(evidence, "file_link", "") or "").strip():
        return True
    if bool(getattr(evidence, "file", None)):
        return True
    return evidence.files.filter(deleted_at__isnull=True).exists()


def actual_delegate_employee(user, evidence):
    """Sólo responsable ACTUAL de la delegación, no un nombre en el formulario."""
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    if not user.has_perm("registration_validation.add_validation"):
        return None
    profile = getattr(user, "profile", None)
    employee_id = getattr(profile, "employee_id", None)
    if not employee_id:
        return None
    delegation = evidence.activity.author.delegation
    if delegation.responsible_id != employee_id:
        return None
    from organization.models import Employee
    employee = Employee.objects.filter(
        pk=employee_id, deleted_at__isnull=True, status__iexact="Active",
        delegation_id=delegation.pk,
    ).first()
    return employee


def assert_existing_endorsement_immutable(validation):
    """Un aval firmado es histórico; para cambiar la decisión, crear otra validación."""
    if not validation.pk:
        return
    values = (
        "evidence_id", "verifier_id", "decision", "result", "observation",
        "version", "date", "formal_delegate_endorsement",
        "delegate_endorsed_by_id", "delegate_endorsed_at", "deleted_at",
    )
    previous = type(validation).objects.filter(pk=validation.pk).values(*values).first()
    if previous is None or not previous["formal_delegate_endorsement"]:
        return
    if any(getattr(validation, field) != previous[field] for field in values):
        raise ValidationError(
            "El respaldo formal del delegado es inmutable. Para modificar o "
            "revocar la aprobación, registre una nueva validación de la evidencia."
        )


def validate_new_endorsement(validation):
    """Validación en MODELO y en guardado, no sólo en JavaScript/plantilla."""
    if not validation.formal_delegate_endorsement:
        return
    assert_existing_endorsement_immutable(validation)
    if validation.pk:
        old = type(validation).objects.filter(pk=validation.pk).values_list(
            "formal_delegate_endorsement", flat=True,
        ).first()
        if old is not None:
            if not old:
                raise ValidationError(
                    "No se puede convertir una validación antigua en aval formal. "
                    "Registre una nueva validación para dejar constancia."
                )
            return
    user = getattr(validation, "_sgr_endorsement_actor", None)
    if not user or not user.pk or validation.delegate_endorsed_by_id != user.pk:
        raise ValidationError({
            "formal_delegate_endorsement": (
                "El respaldo formal debe ser registrado por la cuenta autenticada "
                "del delegado, desde el formulario de Validaciones."
            ),
        })
    if not validation.evidence_id or not validation.verifier_id:
        raise ValidationError({"formal_delegate_endorsement": "Selecciona la evidencia y el verificador."})
    evidence = validation.evidence
    activity_type = evidence.activity.activity_type
    if activity_type is None or not activity_type.is_congratulation:
        raise ValidationError({
            "formal_delegate_endorsement": "Esta evidencia no corresponde a un tipo clasificado como felicitación.",
        })
    delegate = actual_delegate_employee(user, evidence)
    if delegate is None or delegate.pk != validation.verifier_id:
        raise ValidationError({
            "formal_delegate_endorsement": (
                "El aval debe emitirlo la cuenta del delegado responsable actual, "
                "seleccionado además como funcionario verificador."
            ),
        })
    if validation.decision.strip().casefold() != "approved" or validation.result.strip().casefold() != "approved":
        raise ValidationError({
            "formal_delegate_endorsement": "Para respaldar se requiere decisión Aprobada y resultado Approved.",
        })
    if not (validation.observation or "").strip():
        raise ValidationError({
            "observation": "Indica el fundamento formal del delegado para respaldar la felicitación.",
        })
    if not supporting_document_exists(evidence):
        raise ValidationError({
            "formal_delegate_endorsement": "La felicitación necesita una evidencia documental adjunta o enlace válido.",
        })
    if not validation.delegate_endorsed_at:
        raise ValidationError({
            "formal_delegate_endorsement": "Falta la fecha del aval formal.",
        })
    if validation.delegate_endorsed_at > timezone.now():
        raise ValidationError({
            "formal_delegate_endorsement": "La fecha de respaldo no puede ser futura.",
        })
