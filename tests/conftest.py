"""Tests use a throwaway Mongo database and Django's throwaway Postgres test DB."""
import os
import uuid

os.environ["MONGO_DB"] = f"threeform_test_{uuid.uuid4().hex[:8]}"
os.environ["GATEWAY_TOKEN"] = "test-gateway-token"  # settings may have loaded .env already

import pytest  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from accounts import services as account_services  # noqa: E402
from accounts.models import Account  # noqa: E402
from core import mongo  # noqa: E402
from userprofile.models import Users  # noqa: E402

TENANT = "tenant-test-openid"


@pytest.fixture(scope="session", autouse=True)
def mongo_test_db():
    mongo.ensure_indexes()
    yield mongo.db()
    mongo.client().drop_database(os.environ["MONGO_DB"])


@pytest.fixture(autouse=True)
def clean_mongo(mongo_test_db):
    for name in mongo.COLLECTIONS:
        mongo_test_db[name].delete_many({})
    yield


@pytest.fixture
def people(db):
    Users.objects.create(user_id=0, name="t", openid=TENANT, appid="a", t_code="t", ip="127.0.0.1")
    pic = Account.objects.create(user=User.objects.create_user("pic", password="PicPassword#1"),
                                 tenant_openid=TENANT, staff_id="P1", display_name="PIC", role="PIC")
    em = Account.objects.create(user=User.objects.create_user("em", password="EmPassword#1"),
                                tenant_openid=TENANT, staff_id="E1", display_name="EM", role="EM")
    worker = Account.objects.create(tenant_openid=TENANT, staff_id="1001", display_name="W", role="WORKER")
    device, device_token = account_services.register_device(pic, "Tablet", "WS-01")
    return {"pic": pic, "em": em, "worker": worker, "device": device, "device_token": device_token}


def _client_for(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


@pytest.fixture
def clients(people):
    _, pic_t = account_services.password_login("pic", "PicPassword#1")
    _, em_t = account_services.password_login("em", "EmPassword#1")
    _, _, w_t = account_services.worker_login("1001", people["device_token"])
    return {"pic": _client_for(pic_t), "em": _client_for(em_t), "worker": _client_for(w_t), "anon": APIClient()}
