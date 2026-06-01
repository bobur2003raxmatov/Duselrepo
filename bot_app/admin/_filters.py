"""Qayta ishlatiladigan SimpleListFilter sinflari."""

from django.contrib.admin import SimpleListFilter
from ._constants import KATEGORIYA_MAP, ROLE_LABELS


class KategoriyaFilter(SimpleListFilter):
    title          = "Kategoriya"
    parameter_name = "kategoriya"

    def lookups(self, request, model_admin):
        return [(k, k) for k in KATEGORIYA_MAP]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(action_type__in=KATEGORIYA_MAP.get(self.value(), set()))
        return queryset


class RoleFilter(SimpleListFilter):
    title          = "Lavozim"
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return list(ROLE_LABELS.items())

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(user_role=self.value())
        return queryset
