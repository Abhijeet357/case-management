# cases/templatetags/case_extras.py

from django.template.defaulttags import register

@register.filter
def get_item(dictionary, key):
    """
    Custom template filter to allow accessing a dictionary item with a variable key.
    Usage in template: {{ my_dictionary|get_item:my_variable_key }}
    """
    return dictionary.get(key)