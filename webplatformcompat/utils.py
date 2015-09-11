from django.utils.encoding import force_text
from django.utils.text import slugify
from rest_framework.views import get_view_name as drf_get_view_name


def get_view_name(view_cls, suffix=None):
    name = drf_get_view_name(view_cls, suffix=None)
    if name == 'Api Root':
        return 'API Root'
    else:
        return name


def model_from_obj(obj):
    model = getattr(obj, "model", None)

    if model is not None:
        return model

    queryset = getattr(obj, "queryset", None)

    if queryset is not None:
        return queryset.model

    return None


def model_to_resource_type(model):
    """Return the verbose plural form of a model name, with underscores

    Examples:
    Person -> "people"
    ProfileImage -> "profile_image"
    """
    if model is None:
        return "data"

    return force_text(model._meta.verbose_name_plural)


def slug(string):
    """Return a string where words are connected with hyphens"""
    return slugify(force_text(string))


def snakecase(string):
    """Return a string where words are connected with underscores

    Examples:
    "people" -> "people"
    "profile images" -> "profile_images"
    """
    return slug(string).replace('-', '_')
