from __future__ import unicode_literals

from collections import OrderedDict

import sqlalchemy as sa
from ziggurat_foundations import ZigguratException, noop
from ziggurat_foundations.models.services import BaseService
from ziggurat_foundations.models.base import get_db_session
from ziggurat_foundations.permissions import (
    ANY_PERMISSION,
    ALL_PERMISSIONS,
    PermissionTuple,
    resource_permissions_for_users)


class ZigguratResourceTreeMissingException(ZigguratException):
    pass


class ZigguratResourceTreePathException(ZigguratException):
    pass


class ZigguratResourceOutOfBoundaryException(ZigguratException):
    pass


class ZigguratResourceWrongPositionException(ZigguratException):
    pass


class ResourceService(BaseService):
    @classmethod
    def get(cls, resource_id, db_session=None):
        db_session = get_db_session(db_session)
        return db_session.query(cls.model).get(resource_id)

    @classmethod
    def perms_for_user(cls, instance, user, db_session=None):
        """ returns all permissions that given user has for this resource
            from groups and directly set ones too"""
        db_session = get_db_session(db_session, instance)
        query = db_session.query(
            cls.models_proxy.GroupResourcePermission.group_id.label(
                'owner_id'),
            cls.models_proxy.GroupResourcePermission.perm_name,
            sa.literal('group').label('type'))
        query = query.filter(
            cls.models_proxy.GroupResourcePermission.group_id.in_(
                [gr.id for gr in user.groups]
            )
        )
        query = query.filter(
            cls.models_proxy.GroupResourcePermission.resource_id ==
            instance.resource_id)

        query2 = db_session.query(
            cls.models_proxy.UserResourcePermission.user_id.label('owner_id'),
            cls.models_proxy.UserResourcePermission.perm_name,
            sa.literal('user').label('type'))
        query2 = query2.filter(
            cls.models_proxy.UserResourcePermission.user_id ==
            user.id)
        query2 = query2.filter(
            cls.models_proxy.UserResourcePermission.resource_id ==
            instance.resource_id)
        query = query.union(query2)

        groups_dict = dict([(g.id, g) for g in user.groups])
        perms = [PermissionTuple(user,
                                 row.perm_name,
                                 row.type,
                                 groups_dict.get(row.owner_id) if
                                 row.type == 'group' else None,
                                 instance, False, True) for row in query]

        # include all perms if user is the owner of this resource
        if instance.owner_user_id == user.id:
            perms.append(PermissionTuple(user, ALL_PERMISSIONS, 'user',
                                         None, instance, True, True))
        groups_dict = dict([(g.id, g) for g in user.groups])
        if instance.owner_group_id in groups_dict:
            perms.append(PermissionTuple(user, ALL_PERMISSIONS, 'group',
                                         groups_dict.get(
                                             instance.owner_group_id),
                                         instance, True, True))

        return perms

    @classmethod
    def direct_perms_for_user(cls, instance, user, db_session=None):
        """ returns permissions that given user has for this resource
            without ones inherited from groups that user belongs to"""
        db_session = get_db_session(db_session, instance)
        query = db_session.query(
            cls.models_proxy.UserResourcePermission.user_id,
            cls.models_proxy.UserResourcePermission.perm_name)
        query = query.filter(cls.models_proxy.UserResourcePermission.user_id ==
                             user.id)
        query = query.filter(
            cls.models_proxy.UserResourcePermission.resource_id ==
            instance.resource_id)

        perms = [PermissionTuple(user,
                                 row.perm_name,
                                 'user',
                                 None,
                                 instance, False, True) for row in query]

        # include all perms if user is the owner of this resource
        if instance.owner_user_id == user.id:
            perms.append(PermissionTuple(user, ALL_PERMISSIONS, 'user',
                                         None, instance, True))
        return perms

    @classmethod
    def group_perms_for_user(cls, instance, user, db_session=None):
        """ returns permissions that given user has for this resource
            that are inherited from groups """
        db_session = get_db_session(db_session, instance)
        perms = resource_permissions_for_users(cls.models_proxy,
                                               ANY_PERMISSION,
                                               resource_ids=[
                                                   instance.resource_id],
                                               user_ids=[user.id],
                                               db_session=db_session)
        perms = [p for p in perms if p.type == 'group']
        # include all perms if user is the owner of this resource
        groups_dict = dict([(g.id, g) for g in user.groups])
        if instance.owner_group_id in groups_dict:
            perms.append(PermissionTuple(user, ALL_PERMISSIONS, 'group',
                                         groups_dict.get(
                                             instance.owner_group_id),
                                         instance, True, True))
        return perms

    @classmethod
    def users_for_perm(cls, instance, perm_name, user_ids=None, group_ids=None,
                       limit_group_permissions=False, skip_group_perms=False,
                       db_session=None):
        """ return PermissionTuples for users AND groups that have given
        permission for the resource, perm_name is __any_permission__ then
        users with any permission will be listed
        user_ids - limits the permissions to specific user ids,
        group_ids - limits the permissions to specific group ids,
        limit_group_permissions - should be used if we do not want to have
        user objects returned for group permissions, this might cause performance
        issues for big groups
        skip_group_perms - do not attach group permissions to the resultset
        """
        db_session = get_db_session(db_session, instance)
        users_perms = resource_permissions_for_users(cls.models_proxy,
                                                     [perm_name],
                                                     [instance.resource_id],
                                                     user_ids=user_ids,
                                                     group_ids=group_ids,
                                                     limit_group_permissions=limit_group_permissions,
                                                     skip_group_perms=skip_group_perms,
                                                     db_session=db_session)
        if instance.owner_user_id:
            users_perms.append(
                PermissionTuple(instance.owner,
                                ALL_PERMISSIONS, 'user', None, instance, True,
                                True))
        if instance.owner_group_id and not skip_group_perms:
            for user in instance.owner_group.users:
                users_perms.append(
                    PermissionTuple(user, ALL_PERMISSIONS, 'group',
                                    instance.owner_group, instance, True,
                                    True))

        return users_perms

    @classmethod
    def by_resource_id(cls, resource_id, db_session=None):
        """ fetch the resouce by id """
        db_session = get_db_session(db_session)
        query = db_session.query(cls.model).filter(cls.model.resource_id ==
                                                   int(resource_id))
        return query.first()

    @classmethod
    def perm_by_group_and_perm_name(cls, resource_id, group_id, perm_name,
                                    db_session=None):
        """ fetch permissions by group and permission name"""
        db_session = get_db_session(db_session)
        query = db_session.query(cls.models_proxy.GroupResourcePermission)
        query = query.filter(
            cls.models_proxy.GroupResourcePermission.group_id == group_id)
        query = query.filter(
            cls.models_proxy.GroupResourcePermission.perm_id == perm_name)
        query = query.filter(
            cls.models_proxy.GroupResourcePermission.resource_id == resource_id)
        return query.first()

    @classmethod
    def groups_for_perm(cls, instance, perm_name, group_ids=None,
                        limit_group_permissions=False,
                        db_session=None):
        """ return PermissionTuples for groups that have given
        permission for the resource, perm_name is __any_permission__ then
        users with any permission will be listed
        user_ids - limits the permissions to specific user ids,
        group_ids - limits the permissions to specific group ids,
        """
        db_session = get_db_session(db_session, instance)
        group_perms = resource_permissions_for_users(cls.models_proxy,
                                                     [perm_name],
                                                     [instance.resource_id],
                                                     group_ids=group_ids,
                                                     limit_group_permissions=limit_group_permissions,
                                                     skip_user_perms=True,
                                                     db_session=db_session)
        if instance.owner_group_id:
            for user in instance.owner_group.users:
                group_perms.append(
                    PermissionTuple(user, ALL_PERMISSIONS, 'group',
                                    instance.owner_group, instance, True,
                                    True))

        return group_perms

    @classmethod
    def from_resource_deeper(cls, resource_id=None, limit_depth=1000000,
                             db_session=None):
        """
        This returns you subtree of ordered objects relative
        to the start resource_id (currently only implemented in postgresql)

        :param resource_id:
        :param limit_depth:
        :param db_session:
        :return:
        """
        raw_q = """
            WITH RECURSIVE subtree AS (
                    SELECT res.*, 1 AS depth, res.ordering::CHARACTER VARYING AS sorting,
                    res.resource_id::CHARACTER VARYING AS path
                    FROM resources AS res WHERE res.resource_id = :resource_id
                  UNION ALL
                    SELECT res_u.*, depth+1 AS depth,
                    (st.sorting::CHARACTER VARYING || '/' || res_u.ordering::CHARACTER VARYING ) AS sorting,
                    (st.path::CHARACTER VARYING || '/' || res_u.resource_id::CHARACTER VARYING ) AS path
                    FROM resources res_u, subtree st
                    WHERE res_u.parent_id = st.resource_id
            )
            SELECT * FROM subtree WHERE depth<=:depth ORDER BY sorting;
        """
        db_session = get_db_session(db_session)
        text_obj = sa.text(raw_q)
        query = db_session.query(cls.model, 'depth', 'sorting', 'path')
        query = query.from_statement(text_obj)
        query = query.params(resource_id=resource_id, depth=limit_depth)
        return query

    @classmethod
    def from_parent_deeper(cls, parent_id=None, limit_depth=1000000,
                           db_session=None):
        """
        This returns you subtree of ordered objects relative
        to the start parent_id (currently only implemented in postgresql)

        :param resource_id:
        :param limit_depth:
        :param db_session:
        :return:
        """

        if parent_id:
            limiting_clause = 'res.parent_id = :parent_id'
        else:
            limiting_clause = 'res.parent_id is null'

        raw_q = """
            WITH RECURSIVE subtree AS (
                    SELECT res.*, 1 AS depth, res.ordering::CHARACTER VARYING AS sorting,
                    res.resource_id::CHARACTER VARYING AS path
                    FROM resources AS res WHERE {}
                  UNION ALL
                    SELECT res_u.*, depth+1 AS depth,
                    (st.sorting::CHARACTER VARYING || '/' || res_u.ordering::CHARACTER VARYING ) AS sorting,
                    (st.path::CHARACTER VARYING || '/' || res_u.resource_id::CHARACTER VARYING ) AS path
                    FROM resources res_u, subtree st
                    WHERE res_u.parent_id = st.resource_id
            )
            SELECT * FROM subtree WHERE depth<=:depth ORDER BY sorting;
        """.format(limiting_clause)
        db_session = get_db_session(db_session)
        text_obj = sa.text(raw_q)
        query = db_session.query(cls.model, 'depth', 'sorting', 'path')
        query = query.from_statement(text_obj)
        query = query.params(parent_id=parent_id, depth=limit_depth)
        return query

    @classmethod
    def build_subtree_strut(self, result):
        """
        Returns a dictionary in form of
        {node:Resource, children:{node_id: Resource}}

        :param result:
        :return:
        """
        items = list(result)
        root_elem = {'node': None, 'children': OrderedDict()}
        if len(items) == 0:
            return root_elem
        for i, node in enumerate(items):
            new_elem = {'node': node.Resource, 'children': OrderedDict()}
            path = list(map(int, node.path.split('/')))
            parent_node = root_elem
            normalized_path = path[:-1]
            if normalized_path:
                for path_part in normalized_path:
                    parent_node = parent_node['children'][path_part]
            parent_node['children'][new_elem['node'].resource_id] = new_elem
        return root_elem

    @classmethod
    def path_upper(cls, object_id, limit_depth=1000000, db_session=None):
        """
        This returns you path to root node starting from object_id
            currently only for postgresql

        :param object_id:
        :param limit_depth:
        :param db_session:
        :return:
        """
        raw_q = """
            WITH RECURSIVE subtree AS (
                    SELECT res.*, 1 as depth FROM resources res
                    WHERE res.resource_id = :resource_id
                  UNION ALL
                    SELECT res_u.*, depth+1 as depth
                    FROM resources res_u, subtree st
                    WHERE res_u.resource_id = st.parent_id
            )
            SELECT * FROM subtree WHERE depth<=:depth;
        """
        db_session = get_db_session(db_session)
        q = db_session.query(cls.model).from_statement(sa.text(raw_q)).params(
            resource_id=object_id, depth=limit_depth)
        return q

    @classmethod
    def lock_resource_for_update(cls, resource_id, db_session):
        """
        Selects resource for update to
        :param resource_id:
        :param db_session:
        :return:
        """
        db_session = get_db_session(db_session)
        query = db_session.query(cls.model)
        query = query.filter(cls.model.resource_id == resource_id)
        query = query.with_for_update()
        return query.first()

    @classmethod
    def move_to_position(cls, resource_id, to_position,
                         new_parent_id=noop,
                         db_session=None):
        """
        Moves node to new location in the tree

        :param resource_id: resource to move
        :param to_position: new position
        :param new_parent_id: new parent id
        :param db_session:
        :return:
        """
        db_session = get_db_session(db_session)
        new_parent = None
        item_count = 0
        resource = cls.lock_resource_for_update(
            resource_id=resource_id,
            db_session=db_session)
        parent = cls.lock_resource_for_update(
            resource_id=resource.parent_id,
            db_session=db_session)
        if new_parent_id == resource.parent_id and new_parent_id is not noop:
            raise ZigguratResourceTreePathException(
                'New parent is the same as old parent')
        if new_parent_id is not noop:
            new_parent = cls.lock_resource_for_update(
                resource_id=new_parent_id,
                db_session=db_session)
            if not new_parent and new_parent_id is not None:
                raise ZigguratResourceTreeMissingException(
                    'New parent node not found')
            else:
                result = ResourceService.path_upper(new_parent_id,
                                                    db_session=db_session)
                path_ids = [r.resource_id for r in result]
                if resource_id in path_ids:
                    raise ZigguratResourceTreePathException(
                        'Trying to insert node into itself')
        if to_position == resource.ordering and new_parent_id is noop:
            raise ZigguratResourceWrongPositionException(
                'Position is the same as old one')
        if to_position < 1:
            raise ZigguratResourceOutOfBoundaryException(
                'Position is lower than 1')

        query = db_session.query(cls.model.resource_id)
        parent_id = resource.parent_id if new_parent_id is noop else new_parent_id
        query = query.filter(cls.model.parent_id == parent_id)
        item_count = query.count()
        if (to_position > item_count and new_parent_id is noop) or \
                (to_position > item_count + 1):
            raise ZigguratResourceOutOfBoundaryException(
                'Position is higher than item count')

        # move on same branch
        if new_parent_id is noop:
            order_range = list(sorted((resource.ordering, to_position)))
            move_down = resource.ordering > to_position

            query = db_session.query(cls.model)
            query = query.filter(cls.model.parent_id == parent.resource_id)
            query = query.filter(cls.model.ordering.between(*order_range))
            if move_down:
                query.update({cls.model.ordering: cls.model.ordering + 1},
                             synchronize_session=False)
            else:
                query.update({cls.model.ordering: cls.model.ordering - 1},
                             synchronize_session=False)
            resource.ordering = to_position
            db_session.flush()
        # move between branches
        else:
            query = db_session.query(cls.model)
            query = query.filter(cls.model.parent_id == resource.parent_id)
            query = query.filter(cls.model.ordering > resource.ordering)
            query.update({cls.model.ordering: cls.model.ordering + 1},
                         synchronize_session=False)
            query = db_session.query(cls.model)
            query = query.filter(cls.model.parent_id == new_parent_id)
            query = query.filter(cls.model.ordering >= to_position)
            query.update({cls.model.ordering: cls.model.ordering + 1},
                         synchronize_session=False)
            resource.parent_id = new_parent_id
            resource.ordering = to_position
            db_session.flush()
        return True
