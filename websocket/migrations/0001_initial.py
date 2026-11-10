# Generated for the institutional chat persistence update.
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organization", "0015_role_description_delegation_responsible"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.CharField(max_length=300)),
                ("client_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delegation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="institutional_chat_messages", to="organization.delegation")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="institutional_chat_messages", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ChatReadState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_read_id", models.PositiveBigIntegerField(default=0)),
                ("delegation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="institutional_chat_read_states", to="organization.delegation")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="institutional_chat_read_states", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="chatmessage",
            constraint=models.UniqueConstraint(fields=("sender", "client_id"), name="chat_sender_client_unique"),
        ),
        migrations.AddIndex(
            model_name="chatmessage",
            index=models.Index(fields=["delegation", "id"], name="chat_delegation_msg_idx"),
        ),
        migrations.AddConstraint(
            model_name="chatreadstate",
            constraint=models.UniqueConstraint(fields=("user", "delegation"), name="chat_read_user_delegation_unique"),
        ),
    ]
