from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0004_remove_funcionario_identificador_institucional"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="items_medibles",
            new_name="measurable_items",
        ),
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="id_cargo",
            new_name="position_id",
        ),
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="nombre_cargo",
            new_name="position_name",
        ),
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="servicios",
            new_name="services",
        ),
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="ponderaciones",
            new_name="weightings",
        ),
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="vigencia_inicio",
            new_name="validity_start",
        ),
        migrations.RenameField(
            model_name="cargofuncion",
            old_name="vigencia_fin",
            new_name="validity_end",
        ),
        migrations.RenameField(
            model_name="delegacion",
            old_name="id_delegacion",
            new_name="delegation_id",
        ),
        migrations.RenameField(
            model_name="delegacion",
            old_name="nombre",
            new_name="name",
        ),
        migrations.RenameField(
            model_name="delegacion",
            old_name="estado",
            new_name="status",
        ),
        migrations.RenameField(
            model_name="delegacion",
            old_name="ambito",
            new_name="scope",
        ),
        migrations.RenameField(
            model_name="funcionario",
            old_name="id_funcionario",
            new_name="employee_id",
        ),
        migrations.RenameField(
            model_name="funcionario",
            old_name="nombre",
            new_name="name",
        ),
        migrations.RenameField(
            model_name="funcionario",
            old_name="estado",
            new_name="status",
        ),
        migrations.RenameField(
            model_name="funcionario",
            old_name="delegacion",
            new_name="delegation",
        ),
        migrations.RenameField(
            model_name="funcionario",
            old_name="cargo",
            new_name="position",
        ),
    ]