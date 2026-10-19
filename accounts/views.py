import logging

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core import config

from . import audit, services
from .models import Account, AuditLog, Device
from .permissions import IsManagerOrAbove, IsPIC, IsWorkerOrAbove
from .serializers import AccountSerializer, AuditLogSerializer, DeviceSerializer

logger = logging.getLogger("app")


def _me_payload(account, device=None):
    return {
        "account": AccountSerializer(account).data,
        "device": DeviceSerializer(device).data if device else None,
        "idle_timeout_minutes": int(config.get("auth.manager_idle_timeout_minutes", 30)),
    }


class LoginView(APIView):
    """PIC / Engineering Manager: username + password."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            account, token = services.password_login(request.data.get("username", ""),
                                                     request.data.get("password", ""),
                                                     ip=audit.client_ip(request))
        except services.LoginError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"token": token, **_me_payload(account)})


class WorkerLoginView(APIView):
    """Worker: staff ID only, on a registered device (header X-Device-Token)."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            account, device, token = services.worker_login(request.data.get("staff_id", ""),
                                                           request.META.get("HTTP_X_DEVICE_TOKEN", ""),
                                                           ip=audit.client_ip(request))
        except services.LoginError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"token": token, **_me_payload(account, device)})


class LogoutView(APIView):
    permission_classes = [IsWorkerOrAbove]

    def post(self, request):
        services.logout(request.tf_session)
        return Response({"detail": "Logged out."})


class MeView(APIView):
    permission_classes = [IsWorkerOrAbove]

    def get(self, request):
        session = getattr(request, "tf_session", None)
        return Response(_me_payload(request.user, session.device if session else None))


class CurrentDeviceView(APIView):
    """Worker page start-up: is this tablet registered, and for which workstation?"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        device = services.device_from_token(request.META.get("HTTP_X_DEVICE_TOKEN", ""))
        if device is None:
            return Response({"detail": "Device not authorised. Ask the PIC to register this workstation."},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(DeviceSerializer(device).data)


class DeviceListView(APIView):
    permission_classes = [IsPIC]

    def get(self, request):
        qs = Device.objects.filter(tenant_openid=request.user.tenant_openid)
        return Response(DeviceSerializer(qs, many=True).data)

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        workstation = (request.data.get("workstation") or "").strip()
        if not name or not workstation:
            return Response({"detail": "Name and workstation are required."}, status=400)
        device, raw = services.register_device(request.user, name, workstation, request=request)
        # The raw token is shown ONCE; the tablet stores it locally.
        return Response({"device": DeviceSerializer(device).data, "device_token": raw}, status=201)


class DeviceDetailView(APIView):
    permission_classes = [IsPIC]

    def patch(self, request, pk):
        device = Device.objects.filter(pk=pk, tenant_openid=request.user.tenant_openid).first()
        if device is None:
            return Response({"detail": "Device not found."}, status=404)
        services.set_device_active(request.user, device, bool(request.data.get("is_active")), request=request)
        return Response(DeviceSerializer(device).data)


class AccountListView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        qs = Account.objects.select_related("user").filter(tenant_openid=request.user.tenant_openid)
        role = request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return Response(AccountSerializer(qs, many=True).data)

    @transaction.atomic
    def post(self, request):
        if not IsPIC().has_permission(request, self):
            return Response({"detail": "Only the PIC can add accounts."}, status=403)
        d = request.data
        role = d.get("role")
        if role not in Account.ROLE_RANK:
            return Response({"detail": "Role must be PIC, EM or WORKER."}, status=400)
        if Account.objects.filter(tenant_openid=request.user.tenant_openid, staff_id=d.get("staff_id")).exists():
            return Response({"detail": "Staff ID already used."}, status=400)
        user = None
        if role != Account.ROLE_WORKER:
            username, password = d.get("username", "").strip(), d.get("password", "")
            if not username or User.objects.filter(username=username).exists():
                return Response({"detail": "Username missing or already taken."}, status=400)
            try:
                _validate_new_password(password)
            except ValidationError as exc:
                return Response({"detail": " ".join(exc.messages)}, status=400)
            user = User.objects.create_user(username=username, password=password)
        account = Account.objects.create(user=user, tenant_openid=request.user.tenant_openid,
                                         staff_id=str(d.get("staff_id", "")).strip(),
                                         display_name=d.get("display_name", "").strip(), role=role)
        audit.record(request.user, "account.create", "account", account.pk,
                     after=AccountSerializer(account).data, request=request)
        return Response(AccountSerializer(account).data, status=201)


class AccountDetailView(APIView):
    permission_classes = [IsPIC]

    @transaction.atomic
    def patch(self, request, pk):
        account = Account.objects.select_related("user").filter(pk=pk, tenant_openid=request.user.tenant_openid).first()
        if account is None:
            return Response({"detail": "Account not found."}, status=404)
        before = AccountSerializer(account).data
        d = request.data
        if "is_active" in d:
            if account.pk == request.user.pk and not d["is_active"]:
                return Response({"detail": "You cannot disable your own account."}, status=400)
            account.is_active = bool(d["is_active"])
        if d.get("unlock"):
            account.locked_until, account.failed_logins = None, 0
        if "display_name" in d:
            account.display_name = d["display_name"].strip()
        if d.get("new_password"):
            if account.user is None:
                return Response({"detail": "Workers have no password."}, status=400)
            try:
                _validate_new_password(d["new_password"])
            except ValidationError as exc:
                return Response({"detail": " ".join(exc.messages)}, status=400)
            account.user.set_password(d["new_password"])
            account.user.save()
        account.save()
        after = AccountSerializer(account).data
        audit.record(request.user, "account.update", "account", account.pk, before=before, after=after,
                     reason="password reset" if d.get("new_password") else "", request=request)
        return Response(after)


class AuditListView(APIView):
    permission_classes = [IsPIC]

    def get(self, request):
        qs = AuditLog.objects.filter(tenant_openid=request.user.tenant_openid)
        for field in ("entity_type", "entity_id", "action"):
            if request.query_params.get(field):
                qs = qs.filter(**{field: request.query_params[field]})
        limit = min(int(request.query_params.get("limit", 200)), 1000)
        return Response(AuditLogSerializer(qs[:limit], many=True).data)


def _validate_new_password(password):
    min_len = int(config.get("auth.password_min_length", 10))
    if len(password or "") < min_len:
        raise ValidationError(f"Password must be at least {min_len} characters.")
    validate_password(password)
