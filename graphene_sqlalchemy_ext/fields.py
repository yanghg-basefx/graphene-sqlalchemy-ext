# -*- coding: utf-8 -*-
from functools import partial

import promise
import graphene
import graphql_relay
import graphene_sqlalchemy
from sqlalchemy.orm import Query
from graphql_relay.connection.arrayconnection import cursor_to_offset, offset_to_cursor, connection_from_list_slice

__all__ = ['SQLAlchemyConnectionFieldExt']

_ServerEnumCache = {}


class SQLAlchemyConnectionFieldExt(graphene_sqlalchemy.SQLAlchemyConnectionField):
    """
    provide session manager and query manager
    
    class MySQLConnectionField(SQLAlchemyConnectionFieldExt):
        @classmethod
        def session_mapper(cls):
            return {'default': default_session, 'master': master_session, 'slave': slave_session}
        
        @classmethod
        def server_enum_cls_name(cls):
            return "MySQLServerEnum"  # to avoid created server enum in each subclass
        
        def apply_query_filters(cls, model, query, name=None, **args):
            query = super()
            if name is not None:
                query = query.filter_by(name=name)
            return query
    """
    
    def __init__(self, type, *args, **kwargs):
        from .types import SQLAlchemyObjectTypeExt
        if issubclass(type, graphene.relay.Connection):
            type = type._meta.node
        if issubclass(type, SQLAlchemyObjectTypeExt):
            try:
                model = type._meta.model
                enum, default = graphene_sqlalchemy.utils._sort_enum_for_model(model, name=type.__name__ + 'SortEnum')
                kwargs.setdefault("sort",
                                  graphene.Argument(
                                      graphene.List(enum), default_value=default))
            except Exception:
                raise Exception(
                    'Cannot create sort argument for {}. A model is required. Set the "sort" argument'
                    " to None to disabling the creation of the sort query argument".format(
                        type.__name__
                    )
                )
        kwargs.setdefault('id', graphene.List(graphene.String))
        kwargs.setdefault('_id', graphene.List(graphene.Int))
        super(SQLAlchemyConnectionFieldExt, self).__init__(type, *args, **kwargs)

    @classmethod
    def get_query(cls, model, info, server_name=None, **args):
        """
        get_query from cls.session_mapper
        """
        if not server_name:
            _, server_name = cls.server_enum()
        try:
            session = cls.session_mapper()[server_name]()
        except KeyError:
            raise ValueError('Unsupported server name: {}'.format(server_name))

        query = session.query(model)

        return query

    @classmethod
    def apply_query_filters(cls, model, query, sort=None, id=None, _id=None, **args):
        """
        you could apply new filters by override this method
        """
        if id is not None and _id is not None:
            raise ValueError('Could not pass id and global id at the same time')
        if id is not None and len(id) > 0:
            _id = [graphql_relay.from_global_id(gid)[1] for gid in id]
        if _id is not None and len(_id) > 0:
            query = query.filter(model.id.in_(_id))

        if sort is not None:
            if isinstance(sort, graphene_sqlalchemy.utils.EnumValue):
                query = query.order_by(sort.value)
            else:
                sort = tuple(sort)
                query = query.order_by(*(col.value for col in sort))
        return query

    @classmethod
    def resolve_connection(cls, connection_type, model, info, args, resolved):
        if resolved is None:
            resolved = cls.get_query(model, info, **args)
        if isinstance(resolved, Query):
            resolved = cls.apply_query_filters(model, resolved, **args)
        return cls.connection_from_iterable(resolved, args,
                                            connection_type=connection_type,
                                            pageinfo_type=graphene.relay.PageInfo,
                                            edge_type=connection_type.Edge,
                                            )

    @classmethod
    def connection_resolver(cls, resolver, connection_type, model, root, info, **args):
        resolved = resolver(root, info, **args)

        on_resolve = partial(cls.resolve_connection, connection_type, model, info, args)
        if promise.is_thenable(resolved):
            return promise.Promise.resolve(resolved).then(on_resolve)

        return on_resolve(resolved)

    @classmethod
    def connection_from_iterable(cls, iterable, args=None, connection_type=None, edge_type=None, pageinfo_type=None):
        """
        resolve connection depends on the iterable type
        
        if the iterable type is Query, it will go to connection_from_query, the page operation will be much faster
        than connection_from_list
        """
        if isinstance(iterable, Query):
            connection = cls.connection_from_query(iterable, args,
                                                   connection_type=connection_type,
                                                   pageinfo_type=pageinfo_type or graphene.relay.PageInfo,
                                                   edge_type=edge_type or connection_type.Edge,
                                                   )
        else:
            _list = list(iterable)
            connection = cls.connection_from_list(iterable, args,
                                                  connection_type=connection_type,
                                                  pageinfo_type=pageinfo_type or graphene.relay.PageInfo,
                                                  edge_type=edge_type or connection_type.Edge,
                                                  )
        connection.iterable = iterable
        return connection

    @classmethod
    def connection_from_query(cls, query, args=None,
                              connection_type=None, edge_type=None, pageinfo_type=None):
        """
        similar to connection_from_list, but replace some of page operations to database limit...offset...
        it will be much faster and save more memory
        """
        connection_type = connection_type or graphene.relay.Connection
        edge_type = edge_type or connection_type.Edge
        pageinfo_type = pageinfo_type or graphene.relay.PageInfo

        args = args or {}

        before = cursor_to_offset(args.get('before', ''))
        after = cursor_to_offset(args.get('after', ''))
        first = args.get('first', None)
        last = args.get('last', None)

        offset = 0
        limit = None
        slice_start = None

        if after is not None:
            offset = after + 1
        if before is not None:
            limit = max(before - offset, 0)
            if first is not None:
                limit = min(limit, first)
            elif last is not None:
                offset = max(before - last, offset)
                limit = max(before - offset, 0)
        else:
            if first is not None:
                limit = first
            elif last is not None:
                slice_start = -last

        if limit is not None:
            query = query.limit(limit + 1)
        query = query.offset(offset)
        query_result = list(query)
        _len = len(query_result)

        if limit is not None and _len > limit:
            query_result = query_result[:-1]

        cursor_offset = offset
        if slice_start is not None:
            cursor_offset = offset + _len + slice_start

        edges = [
            edge_type(node=node, cursor=offset_to_cursor(cursor_offset + i))
            for i, node in enumerate(query_result[slice_start:])]

        first_edge_cursor = edges[0].cursor if edges else None
        last_edge_cursor = edges[-1].cursor if edges else None
        first_edge_offset = cursor_to_offset(first_edge_cursor)
        last_edge_offset = cursor_to_offset(last_edge_cursor)
        has_previous_page = bool(
            first_edge_offset and
            last and
            (first_edge_offset > 0 if after is None
             else first_edge_offset > after + 1))
        has_next_page = bool(
            last_edge_cursor and
            first and
            (_len > limit if before is None else last_edge_offset < before - 1))

        return connection_type(
            edges=edges,
            page_info=pageinfo_type(
                start_cursor=first_edge_cursor,
                end_cursor=last_edge_cursor,
                has_previous_page=has_previous_page,
                has_next_page=has_next_page
            )
        )

    @classmethod
    def connection_from_list(cls, _list, args=None,
                             connection_type=None, edge_type=None, pageinfo_type=None):
        _len = len(_list)
        connection = connection_from_list_slice(
            _list, args,
            connection_type=connection_type,
            edge_type=edge_type,
            pageinfo_type=pageinfo_type,
            slice_start=0,
            list_length=_len,
            list_slice_length=_len)
        connection.length = _len
        return connection

    @classmethod
    def session_mapper(cls):
        raise NotImplementedError

    @classmethod
    def server_enum_cls_name(cls):
        return cls.__name__ + 'ServerEnum'

    @classmethod
    def server_enum(cls):
        """
        generate server enum from cls.session_mapper, so users can choose which server they want to connect to
        """
        enum_cls_name = cls.server_enum_cls_name()
        if enum_cls_name not in _ServerEnumCache:
            server_names = list(cls.session_mapper().keys())
            assert len(server_names) > 0, 'Session mapper must be provided!'
            if 'DEFAULT' in server_names:
                default = 'DEFAULT'
            else:
                default = server_names[0]
            _ServerEnumCache[enum_cls_name] = (graphene.Enum(enum_cls_name,
                                                             [(server_name, server_name)
                                                              for server_name in server_names]),
                                               default)
        return _ServerEnumCache[enum_cls_name]

    @classmethod
    def server_enum_argument(cls, default_value=None):
        enum, default = cls.server_enum()
        return graphene.Argument(enum, default_value=default_value or default)
