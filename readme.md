Graphene SQLAlchemy Extensions
====================

As you can see, though graphene-sqlalchemy done a lot for us, it still has some
shortcomings. To solve them, I wrote some extensions, and I'm glad you to write 
more extensions.

Connection Field
--------------------

Original SQLAlchemyConnectionField close to completely rewritten, except few
code snippets. New field contains a session manager and a paging device with an
extensible structure.

This field can't be used directly, at least you need to implement the class
method **session_mapper** in sub-class. This method must return a dict which
maps session names to scoped session instances. The session names will be
converted to a selectable enum argument field provides to frontend. User can
select one of these sessions to connect to database. It's useful to support
master-slave databases and read-write separation.

```python
from sqlalchemy.orm import scoped_session, sessionmaker
from graphene_sqlalchemy_ext import SQLAlchemyConnectionFieldExt

master_session = scoped_session(sessionmaker(autocommit=True,
                                             bind=master_engine))
slave_session = scoped_session(sessionmaker(autocommit=True,
                                            bind=slave_engine))
session_mapper = {
    'master_session': master_session,
    'slave_session': slave_session,
    'default': master_session,
}

class ExampleConnectionField(SQLAlchemyConnectionFieldExt):
    @classmethod
    def session_mapper(cls):
        return session_mapper
```

```
{
  examples(server_name: slave_session) {
    ...
  }
}
```

If you want to your query filters, you need to override another method
**apply_query_filters**. You could also extends query arguments.

```python
import graphene
from graphene_sqlalchemy_ext import SQLAlchemyConnectionFieldExt

class ExampleConnectionField(SQLAlchemyConnectionFieldExt):
    def __init__(self, type, *args, **kwargs):
        kwargs.setdefault('name', graphene.String())
        super(ExampleConnectionField, self).__init__(type, *args, **kwargs)

    @classmethod
    def apply_query_filters(cls, model, query, name=None, **args):
        query = super(ExampleConnectionField,
                      cls).apply_query_filters(model, query, **args)
        if name is not None:
            query = query.filter_by(name=name)
        return query
```

```
{
  examples(name: "foo") {
    ...
  }
}
```

Node
--------------------

Original node can't support custom args in sub query. For example, if you have
a parent-children structure in example node, children will not support **sort**
arg.

```python
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class ExampleTable(Base):
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey(id))
    parent = relationship(lambda: ExampleTable,
                          backref=backref('children', lazy='dynamic'),
                          remote_side=id)
```

```
{
  examples(sort: name_asc) {
    edges {
      node {
        children {  # original node doesn't support custom args at this level
          ...
        }
      }
    }
  }
}
```

The reason is graphene-sqlalchemy generate sub field by
**UnsortedSQLAlchemyConnectionField** internal. Easy to see, your custom arg
**name** will not be generated either. So I extend SQLAlchemyObjectType and
add a protected attribute named **\_ConnectionFieldClass**. You need to specify
it to your custom connection field if you do some extensions, then the sub
query can support all the custom args. If not, it will use
BFXGraphQLConnectionField.

```python
from graphene_sqlalchemy_ext import SQLAlchemyObjectTypeExt, SQLAlchemyConnectionFieldExt

class Example(SQLAlchemyObjectTypeExt):
    _ConnectionFieldClass = SQLAlchemyConnectionFieldExt
```

Because of we specified connection class here, so we have another helper
function to simplify you declare your fields.

```python
import graphene
from graphene_sqlalchemy_ext.util import create_connection_field

class Query(graphene.ObjectType):
    examples = create_connection_field(Example)
```

Note: If some args you only want them to be shown at top level, please pass
them when you declare this field instead of define them in init method.

```python
import graphene
from graphene_sqlalchemy_ext import create_connection_field

class Query(graphene.ObjectType):
    examples = create_connection_field(
        Example,
        special_arg=graphene.String(),  # This arg will only be shown at 
                                        # top level
    )
```

Hybrid Property
--------------------

If the records in database is not the actually results, maybe you want to do
a little modification at runtime. SQLAlchemy has a decorator called
hybrid_property can help you do that, and graphene-sqlalchemy also support it.
The problem is, graphene-sqlalchemy does not know what the return type is, so
all the results will be convert to string type. This is not what we excepted.

I extend the hybrid property named **declared_hybrid_property**, which can
declare the property's return type, help graphene-sqlalchemy generate the
correctly fields.

```python
from sqlalchemy import Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from graphene_sqlalchemy_ext import declared_hybrid_property

Base = declarative_base()

class ExampleTable(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String)

    @declared_hybrid_property
    def upper_name(self):
        if isinstance(self, ExampleTable):
            return self.name.upper

    @upper_name.return_type
    def upper_name(self):
        return Column(String)
```
