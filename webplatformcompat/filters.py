from rest_framework.filters import DjangoFilterBackend


class UnorderedDjangoFilterBackend(DjangoFilterBackend):
    """DjangoFilterBackend without ordering and with override"""

    def get_filter_class(self, view, queryset=None):
        """
        Return the django-filters `FilterSet` used to filter the queryset.

        Same as DjangoFilterBackend.get_filter_class, but asserts filter_class
        is never set, and sets order_by is False.
        """
        filter_class = getattr(view, 'filter_class', None)
        filter_fields = getattr(view, 'filter_fields', None)
        assert not filter_class

        if filter_fields:  # pragma: no cover
            class AutoFilterSet(self.default_filter_set):
                class Meta:
                    model = queryset.model
                    fields = filter_fields
                    order_by = False
            return AutoFilterSet

        return None  # pragma: no cover

    def filter_queryset(self, request, queryset, view):
        """
        Filter the queryset by the request and initialization

        filter by initialization is used by the resource actions.
        """
        filter_class = self.get_filter_class(view, queryset)

        if filter_class:
            query_params = request.query_params.dict()
            query_params.update(view.kwargs.get('apply_filter', {}))
            return filter_class(query_params, queryset=queryset).qs
