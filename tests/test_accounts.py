import pytest

from accounts import services
from accounts.models import AuditLog

pytestmark = pytest.mark.django_db
API = "/api/v1"


def test_password_login_and_lockout(people, settings):
    with pytest.raises(services.LoginError):
        services.password_login("pic", "wrong")
    for _ in range(5):
        with pytest.raises(services.LoginError):
            services.password_login("pic", "wrong")
    people["pic"].refresh_from_db()
    assert people["pic"].is_locked()
    with pytest.raises(services.LoginError, match="locked"):
        services.password_login("pic", "PicPassword#1")


def test_workers_cannot_use_password_login(people):
    with pytest.raises(services.LoginError):
        services.password_login("1001", "")


def test_worker_login_needs_registered_device(people):
    with pytest.raises(services.LoginError, match="Device not authorised"):
        services.worker_login("1001", "made-up-token")
    account, device, token = services.worker_login("1001", people["device_token"])
    assert account.role == "WORKER" and device.workstation == "WS-01" and token


def test_revoked_device_ends_worker_sessions(people, clients):
    assert clients["worker"].get(f"{API}/auth/me").status_code == 200
    services.set_device_active(people["pic"], people["device"], False)
    assert clients["worker"].get(f"{API}/auth/me").status_code in (401, 403)


def test_role_permissions(clients):
    assert clients["anon"].get(f"{API}/mes/progress").status_code in (401, 403)
    assert clients["worker"].get(f"{API}/mes/progress").status_code == 403
    assert clients["em"].get(f"{API}/mes/progress").status_code == 200
    assert clients["em"].post(f"{API}/devices", {"name": "x", "workstation": "WS-02"}, format="json").status_code == 403
    assert clients["pic"].post(f"{API}/devices", {"name": "x", "workstation": "WS-02"}, format="json").status_code == 201
    assert clients["worker"].get("/goods/").status_code == 403


def test_worker_is_locked_to_own_workstation(clients):
    assert clients["worker"].get(f"{API}/mes/workstations/WS-02/board").status_code == 403
    assert clients["worker"].get(f"{API}/mes/workstations/WS-01/board").status_code == 200


def test_audit_log_cannot_change(people):
    entry = AuditLog.objects.first()  # device.register from the fixture
    assert entry is not None
    entry.reason = "tamper"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
