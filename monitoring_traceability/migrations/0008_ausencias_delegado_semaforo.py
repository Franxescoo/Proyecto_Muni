# SGR: ausencias informadas por delegado, auditoría e integridad.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('monitoring_traceability', '0007_monitoring_rules_alert_review'),
        ('organization', '0021_merge_0020_employeehistory_0020_position_role_groups'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='EmployeeAbsence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('start_date', models.DateField(verbose_name='Desde')),
                ('end_date', models.DateField(verbose_name='Hasta')),
                ('absence_type', models.CharField(choices=[('LICENSE', 'Licencia'), ('VACATION', 'Vacaciones'), ('PERMISSION', 'Permiso'), ('OTHER', 'Otra ausencia justificada')], max_length=12)),
                ('reason', models.TextField(verbose_name='Motivo del reporte')),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancel_reason', models.TextField(blank=True)),
                ('cancelled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cancelled_employee_absences', to=settings.AUTH_USER_MODEL)),
                ('reported_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reported_absences', to=settings.AUTH_USER_MODEL, verbose_name='Usuario delegado informante')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reported_absences', to='organization.employee', verbose_name='Funcionario ausente')),
                ('delegation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='employee_absences', to='organization.delegation', verbose_name='Delegación que informa')),
            ],
            options={'verbose_name': 'Ausencia informada por delegado', 'verbose_name_plural': 'Ausencias informadas por delegado', 'ordering': ('-created_at', '-pk')},
        ),
        migrations.AddIndex(
            model_name='employeeabsence',
            index=models.Index(fields=['employee', 'start_date', 'end_date'], name='sgr_abs_emp_dates_idx'),
        ),
    ]
