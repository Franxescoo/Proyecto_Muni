from django.contrib import admin

from .models import ChatMessage, ChatReadState


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "delegation", "sender", "created_at")
    list_filter = ("delegation", "created_at")
    search_fields = ("message", "sender__username")
    readonly_fields = ("delegation", "sender", "message", "client_id", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ChatReadState)
class ChatReadStateAdmin(admin.ModelAdmin):
    list_display = ("user", "delegation", "last_read_id")
    readonly_fields = ("user", "delegation", "last_read_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
