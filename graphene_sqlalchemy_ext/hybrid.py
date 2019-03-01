# -*- coding: utf-8 -*-
from sqlalchemy.ext.hybrid import hybrid_property

__all__ = ['declared_hybrid_property']


class declared_hybrid_property(hybrid_property):
    def __init__(self, fget, fset=None, fdel=None,
                 expr=None, custom_comparator=None, update_expr=None, return_type_func=None):
        super(declared_hybrid_property, self).__init__(fget=fget, fset=fset, fdel=fdel, expr=expr,
                                                       custom_comparator=custom_comparator, update_expr=update_expr)
        self.return_type_func = return_type_func
        self._declared_return_type = None

    def __get__(self, instance, owner):
        if self._declared_return_type is None and instance is None:
            self._declared_return_type = self.return_type_func(owner)
        return super(declared_hybrid_property, self).__get__(instance, owner)

    def return_type(self, return_type_func):
        return self._copy(return_type_func=return_type_func)
