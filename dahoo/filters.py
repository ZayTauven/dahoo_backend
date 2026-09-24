from rest_framework import filters


class SearchFilter(filters.SearchFilter):
    """`?search=` : actif (et documenté) uniquement sur les vues qui déclarent `search_fields`."""

    def get_schema_operation_parameters(self, view):
        if not getattr(view, "search_fields", None):
            return []
        return super().get_schema_operation_parameters(view)


class OrderingFilter(filters.OrderingFilter):
    """
    `?ordering=` : limité aux champs listés dans `ordering_fields` de la vue.
    Sans liste explicite, aucun tri n'est accepté (DRF autoriserait sinon tous les champs
    du sérialiseur, y compris des libellés calculés qui provoqueraient une erreur 500).
    """

    def get_default_valid_fields(self, queryset, view, context=None):
        return []

    def get_schema_operation_parameters(self, view):
        if not getattr(view, "ordering_fields", None):
            return []
        return super().get_schema_operation_parameters(view)
