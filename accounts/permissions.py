"""Role checks. PIC (3) > Eng. Manager (2) > Worker (1)."""
from rest_framework.permissions import BasePermission

from .models import Account


class _MinRole(BasePermission):
    min_role = Account.ROLE_PIC
    message = "Your role is not allowed to do this."

    def has_permission(self, request, view):
        user = request.user
        return isinstance(user, Account) and user.rank >= Account.ROLE_RANK[self.min_role]


class IsPIC(_MinRole):
    min_role = Account.ROLE_PIC
    message = "Only the PIC can do this."


class IsManagerOrAbove(_MinRole):
    min_role = Account.ROLE_EM
    message = "Only the PIC or Engineering Manager can do this."


class IsWorkerOrAbove(_MinRole):
    min_role = Account.ROLE_WORKER
    message = "Please log in."
