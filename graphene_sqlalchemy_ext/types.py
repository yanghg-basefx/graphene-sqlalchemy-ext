# -*- coding: utf-8 -*-
import graphene
from graphene.types.utils import yank_fields_from_attrs
import graphene_sqlalchemy

from .fields import SQLAlchemyConnectionFieldExt
from .util import construct_fields

__all__ = ['SQLAlchemyObjectTypeExt']


class SQLAlchemyObjectTypeExt(graphene_sqlalchemy.SQLAlchemyObjectType):
    """
    provide support for declared_hybrid_property and _ConnectionFieldClass
    
    you could use sort argument in subquery without any change
    """
    
    _ConnectionFieldClass = SQLAlchemyConnectionFieldExt

    @classmethod
    def __init_subclass_with_meta__(
            cls,
            model=None,
            registry=None,
            only_fields=(),
            exclude_fields=(),
            interfaces=(graphene.relay.Node,),
            **options
    ):
        super(SQLAlchemyObjectTypeExt, cls).__init_subclass_with_meta__(model=model,
                                                                        registry=registry,
                                                                        only_fields=only_fields,
                                                                        exclude_fields=exclude_fields,
                                                                        interfaces=interfaces,
                                                                        **options)
        sqla_fields = yank_fields_from_attrs(
            construct_fields(cls.__name__, model, registry, only_fields, exclude_fields), _as=graphene.Field
        )
        cls._meta.fields.update(sqla_fields)

    @classmethod
    def get_query(cls, info):
        model = cls._meta.model
        return cls._ConnectionFieldClass.get_query(model, info)

    class Meta:
        abstract = True
