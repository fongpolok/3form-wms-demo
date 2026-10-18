from rest_framework import serializers

from .models import Account, AuditLog, Device


class AccountSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, default=None)
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ["id", "username", "staff_id", "display_name", "role", "is_active", "is_locked",
                  "legacy_staff_pk", "created_at"]

    def get_is_locked(self, obj):
        return obj.is_locked()


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["id", "name", "workstation", "token_hint", "is_active", "created_at", "last_seen"]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "ts", "actor_name", "actor_role", "action", "entity_type", "entity_id",
                  "before", "after", "reason", "ip"]
