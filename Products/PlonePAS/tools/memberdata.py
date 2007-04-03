##############################################################################
#
# PlonePAS - Adapt PluggableAuthService for use in Plone
# Copyright (C) 2005 Enfold Systems, Kapil Thangavelu, et al
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this
# distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""
"""
from Globals import InitializeClass
from Acquisition import aq_base
from AccessControl import ClassSecurityInfo

from zope.interface import implementedBy

from Products.CMFPlone.MemberDataTool import MemberDataTool as BaseMemberDataTool

from Products.CMFCore.MemberDataTool import MemberData as BaseMemberData


from Products.CMFCore.utils import getToolByName
from Products.CMFCore.MemberDataTool import CleanupTemp
from Products.CMFPlone.MemberDataTool import _marker

from Products.PluggableAuthService.utils import classImplements
from Products.PluggableAuthService.interfaces.authservice import IPluggableAuthService
from Products.PluggableAuthService.interfaces.plugins import IPropertiesPlugin, IRoleAssignerPlugin

from Products.PlonePAS.interfaces.plugins import IUserManagement
from Products.PlonePAS.interfaces.group import IGroupManagement
from Products.PlonePAS.interfaces.propertysheets import IMutablePropertySheet
from Products.PlonePAS.interfaces.capabilities import IDeleteCapability, IPasswordSetCapability
from Products.PlonePAS.interfaces.capabilities import IGroupCapability, IAssignRoleCapability
from Products.PlonePAS.interfaces.capabilities import IManageCapabilities
from Products.PlonePAS.utils import getCharset
from Products.PlonePAS.utils import postonly


class MemberDataTool(BaseMemberDataTool):
    """PAS-specific implementation of memberdata tool. Uses Plone
    MemberDataTool as a base.
    """

    meta_type = "PlonePAS MemberData Tool"

    #### an exact copy from the base, so that we pick up the new MemberData.
    #### wrapUser should have a MemberData factory method to over-ride (or even
    #### set at run-time!) so that we don't have to do this.
    def wrapUser(self, u):
        '''
        If possible, returns the Member object that corresponds
        to the given User object.
        We override this to ensure OUR MemberData class is used
        '''
        id = u.getId()
        members = self._members
        if not members.has_key(id):
            # Get a temporary member that might be
            # registered later via registerMemberData().
            temps = self._v_temps
            if temps is not None and temps.has_key(id):
                m = temps[id]
            else:
                base = aq_base(self)
                m = MemberData(base, id)
                if temps is None:
                    self._v_temps = {id:m}
                    if hasattr(self, 'REQUEST'):
                        # No REQUEST during tests.
                        self.REQUEST._hold(CleanupTemp(self))
                else:
                    temps[id] = m
        else:
            m = members[id]
        # Return a wrapper with self as containment and
        # the user as context.
        return m.__of__(self).__of__(u)

#    ## use the default implementation instead; this doesn't meet the original expectation
#    ## (I also don't think this is used anywhere!)
#    def searchFulltextForMembers(self, s):
#        """PAS-specific search for members by id, email, full name.
#        """
#        acl_users = getToolByName( self, 'acl_users')
#        return acl_users.searchUsers(name=s, exact_match=False)
#        # I don't think this is right: we need to return Members

    def deleteMemberData(self, member_id, REQUEST=None):
        """ Delete member data of specified member.
        """
        sheets = None
        if IPluggableAuthService.providedBy(self.acl_users):
            # It's a PAS! Whee!
            # XXX: can we safely assume that user name == member_id
            plugins = self._getPlugins()
            prop_managers = plugins.listPlugins(IPropertiesPlugin)
            for mid, prop_manager in prop_managers:
                # Not all PropertiesPlugins support user deletion
                try:
                    prop_manager.deleteUser(member_id)
                except AttributeError:
                    pass

        # we won't always have PlonePAS users, due to acquisition,
        # nor are guaranteed property sheets
        if not sheets:
            members = self._members
            if members.has_key(member_id):
                del members[member_id]
                return 1
            else:
                return 0
    deleteMemberData = postonly(deleteMemberData)

    ## plugin getter
    def _getPlugins(self):
        return self.acl_users.plugins


InitializeClass(MemberDataTool)


class MemberData(BaseMemberData):

    security = ClassSecurityInfo()

    ## setProperties uses setMemberProperties. no need to override.

    def setMemberProperties(self, mapping, force_local = 0):
        """PAS-specific method to set the properties of a
        member. Ignores 'force_local', which is not reliably present.
        """
        sheets = None

        # We could pay attention to force_local here...
        if not IPluggableAuthService.providedBy(self.acl_users):
            # Defer to base impl in absence of PAS, a PAS user, or
            # property sheets
            return BaseMemberData.setMemberProperties(self, mapping)
        else:
            # It's a PAS! Whee!
            user = self.getUser()
            sheets = getattr(user, 'getOrderedPropertySheets', lambda: None)()

            # We won't always have PlonePAS users, due to acquisition,
            # nor are guaranteed property sheets
            if not sheets:
                # Defer to base impl if we have a PAS but no property
                # sheets.
                return BaseMemberData.setMemberProperties(self, mapping)

        # If we got this far, we have a PAS and some property sheets.
        # XXX track values set to defer to default impl
        # property routing?
        modified = False
        for k, v in mapping.items():
            for sheet in sheets:
                if not sheet.hasProperty(k):
                    continue
                if IMutablePropertySheet.providedBy(sheet):
                    sheet.setProperty(user, k, v)
                    modified = True
                else:
                    break
                    #raise RuntimeError, ("Mutable property provider "
                    #                     "shadowed by read only provider")
        if modified:
            self.notifyModified()

    def getProperty(self, id, default=_marker):
        """PAS-specific method to fetch a user's properties. Looks
        through the ordered property sheets.
        """
        sheets = None
        if not IPluggableAuthService.providedBy(self.acl_users):
            return BaseMemberData.getProperty(self, id)
        else:
            # It's a PAS! Whee!
            user = self.getUser()
            sheets = getattr(user, 'getOrderedPropertySheets', lambda: None)()

            # we won't always have PlonePAS users, due to acquisition,
            # nor are guaranteed property sheets
            if not sheets:
                return BaseMemberData.getProperty(self, id, default)

        charset = getCharset(self)

        # If we made this far, we found a PAS and some property sheets.
        for sheet in sheets:
            if sheet.hasProperty(id):
                # Return the first one that has the property.
                value = sheet.getProperty(id)
                if isinstance(value, unicode):
                    # XXX Temporarily work around the fact that
                    # property sheets blindly store and return
                    # unicode. This is sub-optimal and should be
                    # dealed with at the property sheets level by
                    # using Zope's converters.
                    return value.encode(charset)
                return value

        # Couldn't find the property in the property sheets. Try to
        # delegate back to the base implementation.
        return BaseMemberData.getProperty(self, id, default)


    def getPassword(self):
        """Returns None. Present to avoid NotImplementedError."""
        return None


    ## IManageCapabilities methods

    def canDelete(self):
        """True iff user can be removed from the Plone UI."""
        # IUserManagement provides doDeleteUser
        plugins = self._getPlugins()
        managers = plugins.listPlugins(IUserManagement)
        if managers:
            for mid, manager in managers:
                if IDeleteCapability.providedBy(manager):
                    return manager.allowDeletePrincipal(self.getId())
        return 0


    def canPasswordSet(self):
        """True iff user can change password."""
        # IUserManagement provides doChangeUser
        plugins = self._getPlugins()
        managers = plugins.listPlugins(IUserManagement)
        if managers:
            for mid, manager in managers:
                if IPasswordSetCapability.providedBy(manager):
                    return manager.allowPasswordSet(self.getId())
        return 0

    def passwordInClear(self):
        """True iff password can be retrieved in the clear (not hashed.)

        False for PAS. It provides no API for getting passwords,
        though it would be possible to add one in the future.
        """
        return 0

    def _memberdataHasProperty(self, prop_name):
        mdata = getToolByName(self, 'portal_memberdata', None)
        if mdata:
            return mdata.hasProperty(prop_name)
        return 0


    def canWriteProperty(self, prop_name):
        """True iff the member/group property named in 'prop_name'
        can be changed.
        """
        if not IPluggableAuthService.providedBy(self.acl_users):
            # not PAS; Memberdata is writable
            return self._memberdataHasProperty(prop_name)
        else:
            # it's PAS
            user = self.getUser()
            sheets = getattr(user, 'getOrderedPropertySheets', lambda: None)()
            if not sheets:
                return self._memberdataHasProperty(prop_name)

            for sheet in sheets:
                if not sheet.hasProperty(prop_name):
                    continue
                if IMutablePropertySheet.providedBy(sheet):
                    return 1
                else:
                    break  # shadowed by read-only
        return 0


    def canAddToGroup(self, group_id):
        """True iff member can be added to group."""
        # IGroupManagement provides IGroupCapability
        plugins = self._getPlugins()
        managers = plugins.listPlugins(IGroupManagement)
        if managers:
            for mid, manager in managers:
                if IGroupCapability.providedBy(manager):
                    return manager.allowGroupAdd(self.getId(), group_id)
        return 0

    def canRemoveFromGroup(self, group_id):
        """True iff member can be removed from group."""
        # IGroupManagement provides IGroupCapability
        plugins = self._getPlugins()
        managers = plugins.listPlugins(IGroupManagement)
        if managers:
            for mid, manager in managers:
                if IGroupCapability.providedBy(manager):
                    return manager.allowGroupRemove(self.getId(), group_id)
        return 0


    def canAssignRole(self, role_id):
        """True iff member can be assigned role. Role id is string."""
        # IRoleAssignerPlugin provides IAssignRoleCapability
        plugins = self._getPlugins()
        managers = plugins.listPlugins(IRoleAssignerPlugin)
        if managers:
            for mid, manager in managers:
                if IAssignRoleCapability.providedBy(manager):
                    return manager.allowRoleAssign(self.getId(), role_id)
        return 0



    ## plugin getters

    security.declarePrivate('_getPlugins')
    def _getPlugins(self):
        return self.acl_users.plugins

classImplements(MemberData,
                implementedBy(BaseMemberData),
                IManageCapabilities)

InitializeClass(MemberData)
