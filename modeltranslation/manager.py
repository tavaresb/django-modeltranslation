"""
The idea of MultilingualManager is taken from
django-linguo by Zach Mathew
https://github.com/zmathew/django-linguo

Modeltranslation implementation based on
django-modeltranslation-wrapper by Jacek Tomaszewski
https://github.com/zlorf/django-modeltranslation-wrapper
"""
from django.db import models
from django.db.models.fields.related import RelatedField
from django.utils.translation import get_language
from django.utils.tree import Node

from modeltranslation import translator
from modeltranslation import settings as mt_settings
from modeltranslation.utils import build_localized_fieldname


_registry = {}


def get_translatable_fields_for_model(model):
    if model not in _registry:
        try:
            _registry[model] = dict(
                translator.translator.get_options_for_model(
                    model).localized_fieldnames)
        except translator.NotRegistered:
            _registry[model] = None
    return _registry[model]


def rewrite_lookup_key(model, lookup_key):
    translatable_fields = get_translatable_fields_for_model(model)
    lang = get_language()

    if lang != mt_settings.DEFAULT_LANGUAGE:
        if translatable_fields is not None:
            pieces = lookup_key.split('__')

            # If we are doing a lookup on a translatable field,
            # we want to rewrite it to the actual field name
            # For example, we want to rewrite "name__startswith" to
            # "name_fr__startswith"
            if pieces[0] in translatable_fields:
                lookup_key = build_localized_fieldname(
                    pieces[0], lang.replace('-', '_'))
                remaining_lookup = '__'.join(pieces[1:])
                if remaining_lookup:
                    lookup_key = '%s__%s' % (lookup_key, remaining_lookup)

        pieces = lookup_key.split('__')
        if len(pieces) > 1:
            # Check if we are doing a lookup to a related trans model
            fields_to_trans_models = get_fields_to_translatable_models(model)
            for field_to_trans, transmodel in fields_to_trans_models:
                if pieces[0] == field_to_trans:
                    sub_lookup = '__'.join(pieces[1:])
                    if sub_lookup:
                        sub_lookup = rewrite_lookup_key(transmodel, sub_lookup)
                        lookup_key = '%s__%s' % (pieces[0], sub_lookup)
                    break

    return lookup_key


def get_fields_to_translatable_models(model):
    results = []
    for field_name in model._meta.get_all_field_names():
        field_object, modelclass, direct, m2m = model._meta.get_field_by_name(
            field_name)
        if direct and isinstance(field_object, RelatedField):
            if get_translatable_fields_for_model(
                    field_object.related.parent_model) is not None:
                results.append((field_name, field_object.related.parent_model))
    return results


#class StandardDescriptor(object):
#    def __init__(self, name, initial_val=''):
#        self.name = name
#        self.val = initial_val
#
#    def __set__(self, instance, value):
#        instance.__dict__[self.name] = value
#
#    def __get__(self, instance, owner):
#        return instance.__dict__[self.name]


class MultilingualQuerySet(models.query.QuerySet):
    def __init__(self, *args, **kwargs):
        super(MultilingualQuerySet, self).__init__(*args, **kwargs)
        if self.model and (not self.query.order_by):
            if self.model._meta.ordering:
                # If we have default ordering specified on the model, set it
                # now so that it can be rewritten. Otherwise sql.compiler will
                # grab it directly from _meta
                ordering = []
                for key in self.model._meta.ordering:
                    ordering.append(rewrite_lookup_key(self.model, key))
                self.query.add_ordering(*ordering)

    def _rewrite_q(self, q):
        """
        Rewrites field names inside Q/F call.
        Note: This method was not present in django-linguo.
        """
        if isinstance(q, tuple) and len(q) == 2:
            return rewrite_lookup_key(self.model, q[0]), q[1]
        if isinstance(q, models.F):
            q.name = rewrite_lookup_key(self.model, q.name)
            return q
        if isinstance(q, Node):
            q.children = map(self._rewrite_q, q.children)
        return q

    def _filter_or_exclude(self, negate, *args, **kwargs):
        args = map(self._rewrite_q, args)
        for key, val in kwargs.items():
            new_key = rewrite_lookup_key(self.model, key)
            del kwargs[key]
            kwargs[new_key] = self._rewrite_q(val)
        return super(MultilingualQuerySet, self)._filter_or_exclude(
            negate, *args, **kwargs)

    def order_by(self, *field_names):
        new_args = []
        for key in field_names:
            new_args.append(rewrite_lookup_key(self.model, key))
        return super(MultilingualQuerySet, self).order_by(*new_args)

    def update(self, **kwargs):
        for key, val in kwargs.items():
            new_key = rewrite_lookup_key(self.model, key)
            del kwargs[key]
            kwargs[new_key] = self._rewrite_q(val)
        return super(MultilingualQuerySet, self).update(**kwargs)
    update.alters_data = True

    def language(self, language_code=None):
        """
        TODO: Does nothing at the moment, implement something clever.
        """
        if not language_code:
            return self
        return self

#    def create(self, **kwargs):
#        """
#        Note: This method was not present in django-linguo
#        """
#        translatable_fields = get_translatable_fields_for_model(self.model)
#        #print translatable_fields
#        if translatable_fields is not None:
#            for key, val in kwargs.items():
#                if key in translatable_fields:
#                    # This is our original field. Avoid calling the descriptor
#                    # to update it instead of the current translation field.
#                    print self.model, key
#                    #setattr(self.model, key, StandardDescriptor(key))
#                    setattr(self.model, key, TranslationFieldDescriptor(
#                            key))
#        return super(MultilingualQuerySet, self).create(**kwargs)

#    def create(self, **kwargs):
#        """
#        Note: This method was not present in django-linguo
#        """
#        translatable_fields = get_translatable_fields_for_model(self.model)
#        use_feature = kwargs.pop('_populate', mt_settings.AUTO_POPULATE)
#        if translatable_fields is not None and use_feature:
#            for key, val in kwargs.items():
#                if key in translatable_fields:
#                    # Try to add value in every language
#                    for lang in mt_settings.AVAILABLE_LANGUAGES:
#                        if lang != mt_settings.DEFAULT_LANGUAGE:
#                            new_key = build_localized_fieldname(key, lang)
#                            kwargs.setdefault(new_key, val)
#
##                        if lang == mt_settings.DEFAULT_LANGUAGE:
##                            new_key = key
##                        else:
##                            new_key = build_localized_fieldname(key, lang)
#
#                        #new_key = build_localized_fieldname(key, lang)
#                        #print new_key
#
##                        kwargs.setdefault(new_key, val)
#        return super(MultilingualQuerySet, self).create(**kwargs)


class MultilingualManager(models.Manager):
    use_for_related_fields = True

    def get_query_set(self):
        return MultilingualQuerySet(self.model)

    def language(self, language_code=None):
        return self.get_query_set().language(language_code)
