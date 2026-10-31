from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm


class RecoveryRequestForm(forms.Form):
    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip()

    def find_user(self):
        return get_user_model().objects.filter(
            email__iexact=self.cleaned_data["email"],
            is_active=True,
        ).first()


class RecoveryCodeForm(forms.Form):
    code = forms.CharField(
        label="Código de 6 dígitos",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "maxlength": "6",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdecimal() or len(code) != 6:
            raise forms.ValidationError("Ingresa un código válido de 6 dígitos.")
        return code


class RecoveryPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label="Nueva contraseña",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )
    new_password2 = forms.CharField(
        label="Confirmar nueva contraseña",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].help_text = (
            "Usa al menos 8 caracteres y evita contraseñas comunes."
        )
        self.fields["new_password2"].help_text = (
            "Repite la nueva contraseña para confirmar."
        )

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            raise forms.ValidationError(
                "Las contraseñas no cumplen los requisitos o no coinciden."
            )
