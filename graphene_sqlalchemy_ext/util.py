# -*- coding: utf-8 -*-
from collections import OrderedDict
from typing import Iterable

from sqlalchemy import inspect, Column
from graphene import Union, Dynamic
from graphene import relay
from graphene_sqlalchemy.fields import registerConnectionFieldFactory
from graphene_sqlalchemy.converter import convert_sqlalchemy_column
from graphene_sqlalchemy.registry import get_global_registry

from .hybrid import declared_hybrid_property
from .fields import SQLAlchemyConnectionFieldExt

__all__ = ['empty_resolver', 'create_connection_field', 'create_index_field']


def empty_resolver(*args):
    return args


def create_connection_field(_type, *args, **kwargs):
    return _get_connection_field_class(_type)(_type, *args, **kwargs)


def create_index_field(_type, *args, **kwargs):
    connection_field_class = _get_connection_field_class(_type)
    if issubclass(connection_field_class, SQLAlchemyConnectionFieldExt):
        kwargs.setdefault('server_name', connection_field_class.server_enum_argument())
    return create_connection_field(_type, *args, **kwargs)


def construct_fields(node_name, model, registry=None, only_fields=(), exclude_fields=()):
    inspected_model = inspect(model)
    fields = OrderedDict()
    for hybrid_item in inspected_model.all_orm_descriptors:
        if isinstance(hybrid_item, declared_hybrid_property):
            name = hybrid_item.__name__
            is_not_in_only = only_fields and name not in only_fields
            is_excluded = name in exclude_fields
            if is_not_in_only or is_excluded:
                continue

            fields[name] = _construct_dynamic_type(model, node_name, name, hybrid_item, registry)
    return fields


def _construct_dynamic_type(model, node_name, name, hybrid_item, registry=None):
    def dynamic_type():
        getattr(model, name)
        return _convert_bfx_declared_hybrid_property(node_name + name, hybrid_item, registry)

    return Dynamic(dynamic_type)


def _convert_bfx_declared_hybrid_property(field_name, hybrid_item, registry=None):
    typ = hybrid_item._declared_return_type
    if isinstance(typ, Column):
        return convert_sqlalchemy_column(typ, registry)
    elif isinstance(typ, Iterable):
        models = tuple(typ)
        return _construct_union(field_name + 'Union', models, registry)


def _construct_union(union_name, models, registry=None):
    if registry is None:
        registry = get_global_registry()

    typs = []
    for model in models:
        typ = registry.get_type_for_model(model)
        if typ:
            typs.append(typ)

    class Meta:
        types = typs

    return type(union_name, (Union,), {'Meta': Meta})()


def _get_connection_field_class(_type):
    from .types import SQLAlchemyObjectTypeExt
    from .fields import SQLAlchemyConnectionFieldExt
    if issubclass(_type, relay.Connection):
        _type = _type._meta.node
    if issubclass(_type, SQLAlchemyObjectTypeExt):
        return _type._ConnectionFieldClass
    return SQLAlchemyConnectionFieldExt


registerConnectionFieldFactory(create_connection_field)
