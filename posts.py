from classes import *
import config
from permissions import permit, authorize, authorize_systemuser, authorize_loggedin_or_systemuser
from permissions import authorize_context_owner, authorize_context_member
from errors import abort, doabort, ERRGUT
import types
import uuid
from copy import copy
from mongoengine import Q


#BUG: must die if required stuff is not there. espcially description for a singleton
#will work if singletonmode is not there due to default for tag. Really we should be
#looking up thr tagtype in the database
def augmentspec(specdict, spectype="item"):
    basicdict={}
    print "INSPECDICT", specdict
    if spectype=='item' or spectype=='tag':
        basicdict['creator']=specdict['creator']
        basicdict['name']=specdict['name']
        basicdict['description']=specdict.get('description','')
        if spectype=="item":
            specdict['itemtype']=specdict.get('itemtype','adsgut/item')
            itemtypens=specdict['itemtype'].split('/')[0]
            basicdict['fqin']=itemtypens+"/"+specdict['name']
        else:
            specdict['tagtype']=specdict.get('tagtype','ads/tag')
            specdict['owner']=basicdict['creator']
            #tag, note, library, group and app are reserved and treated as special forms
            basicdict['fqin']=specdict['creator']+"/"+specdict['tagtype']+':'+specdict['name']

        if not specdict.has_key('uri'):
            basicdict['uri']=specdict['name']
        else:
            basicdict['uri']=specdict['uri']
            del specdict['uri']
    specdict['basic']=Basic(**basicdict)
    del specdict['name']
    del specdict['creator']
    if specdict.has_key('description'):
        del specdict['description']
    return specdict

def augmenttypespec(specdict, spectype="itemtype"):
    basicdict={}
    #for itemtype, come in with an app.
    print "INSPECDICT", specdict
    if spectype=='itemtype' or spectype=='tagtype':
        basicdict['creator']=specdict['creator']
        basicdict['name']=specdict['name']
        basicdict['description']=specdict.get('description','')
        basicdict['fqin']=specdict['creator']+"/"+specdict['name']
    specdict['basic']=Basic(**basicdict)
    del specdict['name']
    del specdict['creator']
    if specdict.has_key('description'):
        del specdict['description']
    return specdict

class Postdb():

    def __init__(self, db_session, wdb):
        self.session=db_session
        self.whosdb=wdb
        self.isSystemUser=self.whosdb.isSystemUser
        self.isOwnerOfGroup=self.whosdb.isOwnerOfGroup
        self.isOwnerOfApp=self.whosdb.isOwnerOfApp
        self.isMemberOfGroup=self.whosdb.isMemberOfGroup
        self.isMemberOfApp=self.whosdb.isMemberOfApp

   #######################################################################################################################
   #Internals. No protection on these

    def _getItemType(self, currentuser, fullyQualifiedItemType):
        try:
            itemtype=ItemType.objects(basic__fqin=fullyQualifiedItemType).get()
        except:
            doabort('NOT_FND', "ItemType %s not found" % fullyQualifiedItemType)
        return itemtype

    def _getTagType(self, currentuser, fullyQualifiedTagType):
        try:
            tagtype=TagType.objects(basic__fqin=fullyQualifiedTagType).get()
        except:
            doabort('NOT_FND', "TagType %s not found" % fullyQualifiedTagType)
        return tagtype

    def _getItem(self, currentuser, fullyQualifiedItemName):
        try:
            item=Item.objects(basic__fqin=fullyQualifiedItemName).get()
        except:
            doabort('NOT_FND', "Item %s not found" % fullyQualifiedItemName)
        return item

    def _getTag(self, currentuser, fullyQualifiedTagName):
        try:
            tag=Tag.objects(basic__fqin=fullyQualifiedTagName).get()
        except:
            doabort('NOT_FND', "Tag %s not found" % fullyQualifiedTagName)
        return tag

    def _getSimpleTaggingsByItem(self, currentuser, itemfqin):
        try:
            item=Item.objects(basic__fqin=itemfqin)
        except:
            doabort('NOT_FND', "Item %s not found" % item.fqin)
        return item.stags

    def addItemType(self, currentuser, typespec):
        typespec=augmenttypespec(typespec)
        useras=self.whosdb.getUserForNick(currentuser,typespec['basic'].creator)
        authorize(False, self, currentuser, useras)
        app=self.whosdb.getApp(currentuser, typespec['app'])
        #user must be owner of app whos namespece he is using
        authorize_context_owner(False, self, useras, None, app)
        try:
            itemtype=ItemType(**typespec)
            itemtype.save(safe=True)
        except:
            # import sys
            # print sys.exc_info()
            doabort('BAD_REQ', "Failed adding itemtype %s" % typespec['fqin'])
        return itemtype

    #BUG: completely not dealing with all the things of that itemtype
    def removeItemType(self, currentuser, fullyQualifiedItemType):
        itemtype=self._getItemType(currentuser, fullyQualifiedItemType)
        authorize(False, self, currentuser, currentuser)#any logged in user
        permit(currentuser.nick==itemtype.creator, "User %s not authorized." % currentuser.nick)
        itemtype.delete(safe=True)
        return OK

    def addTagType(self, currentuser, typespec):
        typespec=augmenttypespec(typespec, "tagtype")
        useras=self.whosdb.getUserForNick(currentuser,typespec['basic'].creator)
        authorize(False, self, currentuser, useras)
        try:
            tagtype=TagType(**typespec)
            tagtype.save(safe=True)
        except:
            doabort('BAD_REQ', "Failed adding tagtype %s" % typespec['fqin'])
        return tagtype

    #BUG: completely not dealing with all the things of that itemtype
    def removeTagType(self, currentuser, fullyQualifiedTagType):
        tagtype=self._getTagType(currentuser, fullyQualifiedTagType)
        authorize(False, self, currentuser, currentuser)#any logged in user
        permit(currentuser.nick==tagtype.creator, "User %s not authorized" % currentuser.nick)
        tagtype.delete(safe=True)
        return OK

    #######################################################################################################################

    #multiple postings by the same user, preventded at dbase level by having (i, u, g) id as primary key.
    #THIRD PARTY MASQUERADABLE(TPM) eg current user=oauthed web service acting as user.
    #if item does not exist this will fail.
    def postItemIntoGroup(self, currentuser, useras, fqgn, itemfqin):
        grp=self.whosdb.getGroup(currentuser, fqgn)
        item=self._getItem(currentuser, itemfqin)
        #Does the False have something to do with this being ok if it fails?BUG
        authorize_context_owner(False, self, currentuser, useras, grp)
        permit(self.isMemberOfGroup(useras, grp),
            "Only member of group %s can post into it" % grp.basic.fqin)

        try:#BUG:what if its already there?
            newposting=Post(postfqin=grp.basic.fqin, postedby=useras.nick, thingtopostfqin=itemfqin, thingtoposttype=item.itemtype)
            #newposting.save(safe=True)
            print 'pppppppppppppppp'
            postingdoc=PostingDocument(thing=newposting)
            postingdoc.save(safe=True)
            #Not sure instance updates work but we shall try.
            item.update(safe_update=True, push__pingrps=newposting)
        except:
            import sys
            print sys.exc_info()
            doabort('BAD_REQ', "Failed adding newposting of item %s into group %s." % (item.basic.fqin, grp.basic.fqin))
        personalfqgn=useras.nick+"/group:default"

        if grp.basic.fqin!=personalfqgn:
            if personalfqgn in [ptt.postfqin for ptt in item.pingrps]:
                print "NOT IN PERSONAL GRP"
                self.postItemIntoGroup(currentuser, useras, personalfqgn, itemfqin)
                #self.commit() is this needed?
        #BUG: we are not adding to the app for the itemtype. But lets figure out its
        #semantics first
        #BUG: need idempotenvy in taggings
        #TODO: have posting the taggings into a group be handled by routing and signals
        return item


#######################################################################################################################
    #Stuff for a single item
    #When a web service adds an item on their site, and we add it here as the web service user, do we save the item?
    #If we havent saved the item, can we post it to a group?: no Item id. Must we not make the web service save the
    #item first? YES. But there is no app. Aah this must be done outside in web service!!

    def saveItem(self, currentuser, useras, itemspec):
        #permit(currentuser==useras or self.whosdb.isSystemUser(currentuser), "User %s not authorized or not systemuser" % currentuser.nick)
        authorize(False, self, currentuser, useras)#sysadmin or any logged in user where but cu and ua must be same
        fqgn=useras.nick+"/group:default"
        itemspec=augmentspec(itemspec)
        #Information about user useras goes as namespace into newitem, but should somehow also be in main lookup table
        try:
            print "was the item found?"
            newitem=self._getItem(currentuser, itemspec['basic'].fqin)
            #TODO: do we want to handle an updated saving date here by making an array
            #this way we could count how many times 'saved'
        except:
            #the item was not found. Create it
            print "SO CREATING ITEM %s\n" % itemspec['basic'].fqin
            try:
                print "ITSPEC", itemspec
                newitem=Item(**itemspec)
                newitem.save(safe=True)
                # print "Newitem is", newitem.info()
            except:
                # import sys
                # print sys.exc_info()
                doabort('BAD_REQ', "Failed adding item %s" % itemspec['basic'].fqin)
        #self.session.add(newitem)
        #appstring=newitem.itemtype.app

        #print "APPSTRING\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\", appstring
        #itemtypesapp=self.whosdb.getApp(currentuser, appstring)
        #This is the rewal save!!!
        self.postItemIntoGroup(currentuser, useras, fqgn, newitem.basic.fqin)
        print '**********************'
        #IN LIEU OF ROUTING
        fqan=self._getItemType(currentuser, newitem.itemtype).app
        self.postItemIntoApp(currentuser, useras, fqan, newitem.basic.fqin)
        #NOTE: above is now done via saving item into group, which means to say its auto done on personal group addition
        #But now idempotency, when I add it to various groups, dont want it to be added multiple times
        #thus we'll do it only when things are added to personal groups: which they always are
        print '&&&&&&&&&&&&&&&&&&&&&&', 'FINISHED SAVING'
        return newitem



    def postItemPublic(self, currentuser, useras, fullyQualifiedItemName):
        grp=self.whosdb.getGroup(currentuser, 'adsgut/group:public')
        item=self.postItemIntoGroup(currentuser, useras, grp, fullyQualifiedItemName)
        return item

    def removeItemFromGroup(self, currentuser, useras, fqgn, itemfqin):
        grp=self.whosdb.getGroup(currentuser, fqgn)
        item=self._getItem(currentuser, itemfqin)
        authorize_context_owner(False, self, currentuser, useras, grp)
        permit(useras==postingtoremove.user and self.whosdb.isMemberOfGroup(useras, grp),
            "Only member of group %s who posted this item can remove it from the app" % grp.basic.fqin)
        #NO CODE HERE YET
        return OK

    #deletion semantics with group user not clear at all! TODO: personal group removal only, item remains, are permits ok?
    def deleteItem(self, currentuser, useras, itemfqin):
        authorize(False, self, currentuser, useras)#sysadmin or any logged in user where but cu and ua must be same
        fqgn=useras.nick+"/group:default"
        personalgrp=self.whosdb.getGroup(currentuser, fqgn)
        itemtoremove=self._getItem(currentuser, itemfqin)
        #should we do this. Or merely mark it removed.? TODO
        #protecting the masquerade needs to be done in web service
        permit(useras==itemtoremove.user, "Only user who saved this item can remove it")
        #BUG: is this all? what are the semantics?
        self.removeItemFromGroup(currentuser, useras, personalgrp, itemtoremove)
        return OK
        #What else must be done here?
        #NEW: We did not nececerraily create this, so we cant remove!!! Even so implemen ref count as we can then do popularity
        #self.session.remove(itemtoremove)

    def postItemIntoApp(self, currentuser, useras, fqan, itemfqin):
        app=self.whosdb.getApp(currentuser, fqan)
        item=self._getItem(currentuser, itemfqin)
        authorize_context_owner(False, self, currentuser, useras, app)
        permit(self.whosdb.isMemberOfApp(useras, app),
            "Only member of app %s can post into it" % app.basic.fqin)
        # permit(currentuser==useras or self.whosdb.isOwnerOfApp(currentuser, app) or self.whosdb.isSystemUser(currentuser),
        #     "Current user must be useras or only owner of app %s or systemuser can masquerade as user" % app.fqin)

        try:#BUG:What if its already there?
            newposting=Post(postfqin=app.basic.fqin, postedby=useras.nick, thingtopostfqin=itemfqin, thingtoposttype=item.itemtype)
            #newposting.save(safe=True)
            postingdoc=PostingDocument(thing=newposting)
            postingdoc.save(safe=True)
            item.update(safe_update=True, push__pinapps=newposting)
        except:
            doabort('BAD_REQ', "Failed adding newposting of item %s into app %s." % (item.basic.fqin, app.basic.fqin))
        #COMMENTING OUT as cant think of situation where a post into app ought to trigger personal group saving
        # fqgn=useras.nick+"/group:default"
        # personalgrp=self.whosdb.getGroup(currentuser, fqgn)
        # if item not in personalgrp.itemsposted:
        #     self.postItemIntoGroup(currentuser, useras, personalgrp, item)
        #self.commit() #Needed as otherwise .itemsposted fails:
        #print newitem.groupsin, "WEE", grp.itemsposted
        #grp.groupitems.append(newitem)

        print "FINIAH APP POST"
        return item

    def removeItemFromApp(self, currentuser, useras, fqan, itemfqin):
        app=self.whosdb.getApp(currentuser, fqan)
        item=self._getItem(currentuser, itemfqin)
        authorize_context_owner(False, self, currentuser, useras, app)
        permit(useras==postingtoremove.user and self.whosdb.isMemberOfApp(useras, app),
            "Only member of app %s who posted this item can remove it from the app" % app.basic.fqin)
        #No code as yet
        return OK


    #this is done for making a standalone tag, without tagging anything with it
    ##useful for libraries and such
    def makeTag(self, currentuser, useras, tagspec, tagmode=False):
        tagspec=augmentspec(tagspec, spectype='tag')
        authorize(False, self, currentuser, useras)

        try:
            print "was tha tag found"
            tag=self._getTag(currentuser, tagspec['basic'].fqin)
            #remember that on handover to someone else or a group, fqtn is not changed
            #thus we must check i am member of group, or the person to whom ownership
            #is transferred. if i am not, abort
            if not self.isMemberOfTag(currentuser, tag):
                doabort('NOT_AUT', "Not authorized for tag %s" % tagspec['basic'].fqin)
        except:
            #the tag was not found. Create it
            #BUG we dont even check for the existence of tagtype. These things must be added.
            try:
                print "TRY CREATING TAG"
                tagspec['push__members']=useras.nick
                tag=Tag(**tagspec)
                tag.save(safe=True)
            except:
                import sys
                print sys.exc_info()
                doabort('BAD_REQ', "Failed adding tag %s" % tagspec['basic'].fqin)
        return tag

    #not creating a delete tag until we know what it means
    #
    def deleteTag(self, currentuser, useras, fqtn):
        pass
    #We will have special methods or api's for tag/note/library
    #######################################################################################################################
    # If tag exists we must use it instead of creating new tag: this is useful for rahuldave@gmail.com/tag:statistics
    #or rahuldave@gmail.com/tag:machinelearning. For notes, we expect an autogened name and we wont reuse that note
    #thus multiple names are avoided as each tag is new. But when tagging an item, make sure you are appropriately
    #creating a new tag or reusing an existing one. And that tag is uniqie to the user, so indeeed pavlos/tag:statistics
    #is different
    #what prevents me from using someone elses tag? validatespec DOES
    def tagItem(self, currentuser, useras, fullyQualifiedItemName, tagspec, tagmode=False):
        authorize(False, self, currentuser, useras)
        print "FQIN", fullyQualifiedItemName
        itemtobetagged=self._getItem(currentuser, fullyQualifiedItemName)
        tag = self.makeTag(currentuser, useras, tagspec, tagmode)
        #Now that we have a tag item, we need to create a tagging
        try:
            print "was the itemtag found"
            itemtag=self._getTagging(currentuser, tag, itemtobetagged)
        except:
            print "NOTAGGING YET. CREATING"
            tagtype=self._getTagType(currentuser, tag.tagtype)
            #BUG in tags shouldnt singleton mode enforce a tagdescription, unlike what augmentspec does?
            if tagtype.singletonmode:
                tagdescript=tag.basic.description
            else:
                tagdescript=""
            try:
                itemtag=Tagging(postfqin=tag.basic.fqin,
                                postedby=useras.nick,
                                thingtopostfqin=itemtobetagged.basic.fqin,
                                thingtoposttype=itemtobetagged.itemtype,
                                tagname=tag.basic.name,
                                tagtype=tag.tagtype,
                                tagdescription=tagdescript
                )
                #itemtag.save(safe=True)
                taggingdoc=TaggingDocument(thething=itemtag)
                taggingdoc.save(safe=True)
                print "LALALALALALALALA990"
                if tag.tagtype=="ads/library":
                    itemtobetagged.update(safe_update=True, push__pinlibs=itemtag)
                else:
                    itemtobetagged.update(safe_update=True, push__stags=itemtag)
            except:
                doabort('BAD_REQ', "Failed adding newtagging on item %s with tag %s" % (itemtobetagged.basic.fqin, tag.basic.fqin))

            personalfqgn=useras.nick+"/group:default"
            #personalgrp=self.whosdb.getGroup(currentuser, personalfqgn)
            #Add tag to default personal group
            print "adding to %s" % personalfqgn
            #taggingdoc.reload()
            self.postTaggingIntoGroup(currentuser, useras, personalfqgn, taggingdoc)
        #at this point it goes to the itemtypes app too.
        #This will get the personal, and since no commit, i think we will not hit personal.
        #nevertheless we protect against it below
        #All tagmode stuff to be done via routing
        # if tagmode:
        #     groupsitemisin=itemtobetagged.get_groupsin(useras)
        #     #the groups user is in that item is in: in tagmode we make sure, whatever groups item is in, tags are in
        #     for grp in groupsitemisin:
        #         if grp.fqin!=personalfqgn:
        #             #wont be added to app for these
        #             self.postTaggingIntoGroupFromItemtag(currentuser, useras, grp, itemtag)
        # #print itemtobetagged.itemtags, "WEE", newtag.taggeditems, newtagging.tagtype.name

        #if itemtag found just return it, else create, add to group, return
        return taggingdoc

    def untagItem(self, currentuser, useras, fullyQualifiedTagName, fullyQualifiedItemName):
        #Do not remove item, do not remove tag, do not remove tagging
        #just remove the tag from the personal group
        authorize(False, self, currentuser, useras)
        #POSTPONE until we have refcounting implementation
        #
        # tag=self._getTag(currentuser, fullyQualifiedTagName)
        # itemtobeuntagged=self._getItem(currentuser, fullyQualifiedItemName)
        # #Does not remove the tag or the item. Just the tagging. WE WILL NOT REFCOUNT TAGS
        # taggingtoremove=self._getTagging(currentuser, tag, itemtobeuntagged)
        # permit(useras==taggingtoremove.user, "Only user who saved this item to the tagging %s can remove the tag from priv grp" % tag.fqin )
        # #self.session.remove(taggingtoremove)
        # fqgn=useras.nick+"/group:default"
        # personalgrp=self.whosdb.getGroup(currentuser, fqgn)
        # #remove tag from user's personal group. Keep the tagging around
        # self.removeTaggingFromGroup(currentuser, useras, personalgrp.fqin, itemtobeuntagged.fqin, tag.fqin)
        return OK

    #Is item in group? If not add it? depends on UI schemes
    #
    #
    def isOwnerOfTag(self, currentuser, tag):
        if currentuser.nick==tag.owner:
            return True
        else:
            return False

    def isMemberOfTagO(self, currentuser, tag):
        #tags owner here must be a group
        if self.isOwnerOfTag(currentuser, tag):
            return True
        elif self.whosdb.isMemberOfGroup(currentuser.nick,tag.owner):
            return True
        else:
            return False

    def isMemberOfTag(self, currentuser, tag):
        #tags owner here must be a group
        if currentuser.nick in tag.members:
            return True
        else:
            return False

    #once trnsferroed to a group, cannot be transfered back.
    #for now, u must me member of group to transfer ownership there
    #if you transfer to another person you lose rights
    #groups cant create tags for now, must transfer to group
    def changeOwnershipOfTag(self, currentuser, fqtn, newowner, groupmode=False):
        tagq=Tag.objects(basic__fqin=fqtn)
        if groupmode:
            try:
                groupq=Group.objects(basic__fqin=newowner)
                group=groupq.get()
                newowner=group.basic.fqin
            except:
                #make sure target exists.
                doabort('BAD_REQ', "No such group %s" % newowner)
            authorize_context_member(False, self, currentuser, None, group)
        else:
            try:
                userq= User.objects(nick=newowner)
                newowner=userq.get().nick
            except:
                #make sure target exists.
                doabort('BAD_REQ', "No such user %s" % newowner)
        try:
            tag=tagq.get()
        except:
            doabort('BAD_REQ', "No such group %s" % fqtn)
        authorize_context_owner(False, self, currentuser, None, tag)
        try:
            oldownernick=tag.owner
            if groupmode:
                tag.update(safe_update=True, set__owner = newowner, push__members=newowner)
            else:
                tag.update(safe_update=True, set__owner = newowner, push__members=newowner, pull__members=oldownernick)
        except:
            doabort('BAD_REQ', "Failed changing owner from %s to %s for tag %s" % (oldownernick, newowner, fqtn))
        return newowner

    #DO WE WANT IDEMPOTENCY THING?
    def postTaggingIntoGroup(self, currentuser, useras, fqgn, taggingdoc):
        #permit(currentuser==useras or self.whosdb.isSystemUser(currentuser), "User %s not authorized or not systemuser" % currentuser.nick)
        itemtag=taggingdoc.thething
        #taggingdoc.reload()
        print "FQGN", fqgn
        grp=self.whosdb.getGroup(currentuser, fqgn)
        authorize_context_owner(False, self, currentuser, useras, grp)

        #Information about user useras goes as namespace into newitem, but should somehow also be in main lookup table
        permit(self.whosdb.isMemberOfGroup(useras, grp),
            "Only member of group %s can post into it" % grp.basic.fqin)
        permit(useras.nick==itemtag.postedby,
            "Only creator of tag can post into group %s" % grp.basic.fqin)
        #item=self._getItem(currentuser, itemtag.thingtopostfqin)
        try:
            newposting=Post(postfqin=grp.basic.fqin,
                postedby=useras.nick, thingtopostfqin=itemtag.postfqin, thingtoposttype=itemtag.thingtoposttype)
            #newposting.save(safe=True)
            ##BUG:is a new taggingdoc in order?
            print 'OOOOOOOOOOOO'
            taggingdoc.update(safe_update=True, push__pingrps=newposting)
        except:
            import sys
            print sys.exc_info()
            doabort('BAD_REQ', "Failed adding newtagging on item %s with tag %s in group %s" % (itemtag.thingtopostfqin, itemtag.postfqin, grp.basic.fqin))


        #use routing for make sure we go into itemtypes app?
        #personalfqgn=useras.nick+"/group:default"
        #only when we do post tagging to personal group do we post tagging to app. this ensures app dosent have multiples.
        # if grp.fqin==personalfqgn:
        #     personalgrp=self.whosdb.getGroup(currentuser, personalfqgn)
        #     appstring=itemtag.item.itemtype.app
        #     itemtypesapp=self.whosdb.getApp(currentuser, appstring)
        #     self.postTaggingIntoAppFromItemtag(currentuser, useras, itemtypesapp, itemtag)
        #grp.groupitems.append(newitem)
        # self.commit()
        # print itemtag.groupsin, 'jee', grp.itemtags
        # itgto=self.session.query(TagitemGroup).filter_by(itemtag=itemtag, group=grp).one()
        # print itgto
        return itemtag

    #BUG: currently not sure what the logic for everyone should be on this, or if it should even be supported
    #as other users have now seen stuff in the group. What happens to tagging. Leave alone for now.
    def removeTaggingFromGroup(self, currentuser, useras, fqgn, itemorfullyQualifiedItemName, tagorfullyQualifiedTagName):

        grp=self.whosdb.getGroup(currentuser, fqgn)

        authorize_context_owner(False, self, currentuser, useras, grp)
        #BUG: no other auths. But the model for this must be figured out.
        #The itemtag must exist at first
        # itemtag=self._getTagging(currentuser, tag, item)
        # itgtoberemoved=self.getGroupTagging(currentuser, itemtag, grp)
        # self.session.remove(itgtoberemoved)
        # Removed for now handle via refcounting.
        return OK

    #NOTE: we are not requiring that item be posted into group or that tagging autopost it. FIXME. think we got this
    def postTaggingIntoApp(self, currentuser, useras, fqan, taggingdoc):
        #permit(currentuser==useras or self.whosdb.isSystemUser(currentuser), "User %s not authorized or not systemuser" % currentuser.nick)
        itemtag=taggingdoc.thething
        app=self.whosdb.getApp(currentuser, fqan)
        authorize_context_owner(False, self, currentuser, useras, app)

        #Note tagger need not be creator of item.

        permit(self.whosdb.isMemberOfApp(useras, app),
            "Only member of app %s can post into it" % app.basic.fqin)
        permit(useras.nick==itemtag.postedby,
            "Only creator of tag can post into app %s" % app.basic.fqin)
        # permit(currentuser==useras or self.whosdb.isOwnerOfApp(currentuser, app) or self.whosdb.isSystemUser(currentuser),
        #     "Current user must be useras or only owner of app %s or systemuser can masquerade as user" % app.fqin)

        #The itemtag must exist at first
        #Information about user useras goes as namespace into newitem, but should somehow also be in main lookup table
        try:
            print "make app posting"
            newposting=Post(postfqin=app.basic.fqin,
                postedby=useras.nick, thingtopostfqin=itemtag.postfqin, thingtoposttype=itemtag.thingtoposttype)
            #newposting.save(safe=True)
            taggingdoc.update(safe_update=True, push__pinapps=newposting)
        except:
            doabort('BAD_REQ', "Failed adding newtagging on item %s with tag %s in app %s" % (itemtag.thingtopostfqin, itemtag.postfqin, app.basic.fqin))

        return itemtag



    #BUG: currently not sure what the logic for everyone should be on this, or if it should even be supported
    #as other users have now seen stuff in the group. What happens to tagging. Leave alone for now.
    def removeTaggingFromApp(self, currentuser, useras, fqan, itemorfullyQualifiedItemName, tagorfullyQualifiedTagName):
        app=self.whosdb.getApp(currentuser, fqan)

        authorize_context_owner(False, self, currentuser, useras, app)
        #Bug do properly with refcounting
        return OK

    #######################################################################################################################


    #######################################################################################################################

    #ALL KINDS OF GETS
    #are we impliciting that fqin be guessable? if we use a random, possibly not? BUG
    def _getItemByFqin(self, currentuser, fullyQualifiedItemName):
        #fullyQualifiedItemName=nsuser.nick+"/"+itemname
        #permit(currentuser==useras or self.whosdb.isSystemUser(currentuser), "User %s not authorized or not systemuser" % currentuser.nick)
        authorize(False, self, currentuser, currentuser)#as long as logged on
        try:
            item=Item.objects(basic__fqin=fullyQualifiedItemName).get()
        except:
            doabort('AOK_REQ', "Item with name %s not found." % fullyQualifiedItemName)
        return item

    #the uri can be saved my multiple users, which would give multiple results here. which user to use
    #should we not use useras. Ought we be getting from default group?
    #here I use useras, but suppose the useras is not the user himself or herself (ie currentuser !=useras)
    #then what? In other words if the currentuser is a group or app owner how should things be affected?
    #CURRENTLY DONT ALLOW THIS FUNC TO BE MASQUERADED.
    #We except, but send back a 200, so that a ads page can set that this item was never saved

    #so nor sure how useful as still comes from a users saving
    #BUG: or should we search by uri, no matter who has saved? The system wont allow an item to be created
    #more than once. but, wont uris be reused? unless insist on unique uris. Allowing uris to pick from name
    #we should be ok tho.
    def _getItemsByURI(self, currentuser, useras, itemuri):
        #permit(currentuser==useras or self.whosdb.isSystemUser(currentuser), "User %s not authorized or not systemuser" % currentuser.nick)
        authorize(False, self, currentuser, useras)#as long as logged on, and currentuser=useras
        try:
            items=Item.objects(basic__uri=itemuri, basic__creator=useras.nick)
        except:
            doabort('NOT_FND', "Item with uri %s not saved by %s." % (itemuri, useras.nick))
        return items

    #owner or creator? I say owner, but maybe Q object later on either BUG
    #no notion to group or app context as thats on tagging
    #This allows us to get libraries, etc.
    def _getTagsForUser(self, currentuser, useras, tagtype):
        authorize(False, self, currentuser, useras)#as long as logged on, and currentuser=useras
        try:
            #Bu default, i will only send back stuff owned by this user
            tags=Tag.objects(tagtype=tagtype, owner=useras.nick)
        except:
            doabort('NOT_FND', "Tags with tagtype %s saved by %s. not found" % (tagtype, useras.nick))
        return tags

    #Internal: no permissions, used to get fqtns for every tagging
    def _getTagsForName(self, currentuser, tagname):
        try:
            #Bu default, i will only send back stuff owned by this user
            tags=Tag.objects(basic__name=tagname)
        except:
            doabort('NOT_FND', "Tags with tagname %s not found" % tagname)
        return tags



    # SO HERE WE LIST THE SEARCHES
    #
    #Use cases
    #(0) get tags, as in get libraries, for a group/user/app/type.
    #(1) get items by tags, and tags intersections, tagspec/itemspec in general
    #(2) get tags for item, and tags for item compatible with user
    #(3) get items for group and app, and filter them further: the context filter
    #(4) to filter further down by user, the userthere filter.
    #(5) ordering is important. Set up default orders and allow for sorting

    #searchspec has :
    #   should searchspec have libraries?
    #   context={user:True|False, type:None|group|app, value:None|specificvalue}/None
    #   sort={by:field, ascending:True}/None #currently
    #   criteria=[{field:fieldname, op:operator, value:val}...]
    #   CURRENTLY we use AND outside. To do OR use an op:in query
    #   Finally we need to handle pagination/offsets
    def _makeQuery(self, klass, currentuser, useras, criteria, context=None, sort=None, shownfields=None, pagtuple=None):
        DEFPAGOFFSET=0
        DEFPAGSIZE=10
        kwdict={}
        qterms=[]
        #make sure we are atleast logged in and useras or superuser
        authorize(False, self, currentuser, useras)
        for l in criteria:
            kwdict={}
            for d in l:
                if d['op']=='eq':
                    kwdict[d['field']]=d['value']
                else:
                    kwdict[d['field']+'__'+d['op']]=d['value']
            qterms.append(Q(**kwdict))
        if len(qterms) == 1:
            qclause=qterms[0]
        else:
            qclause = reduce(lambda q1, q2: q1.__and__(q2), qterms)
        #kwdict={d['field']+'__'+d['op']:d['value'] for d in criteria}
        #print "KWDICT", kwdict
        #SHOWNFIELDS=['itemtype', 'basic.fqin', 'basic.description', 'basic.name', 'basic.uri']
        #itemqset=Item.objects.only(*SHOWNFIELDS)
        #print itemqset[0].dtype
        #itemqset=klass.objects(**kwdict)
        #itemqset=itemqset.filter(**kwdict)
        itemqset=klass.objects.filter(qclause)
        
        #For context we must learn to not leak other groups: use exclude or only not to send that info back
        #otherwise must filter it out in python.

        #BUG: does this allow acceess to your posts in a group we belong to ? I tdont think so
        #we may want to support the large query
        if context:
            userthere=context['user']
            ctype=context['type']
            if userthere==True and ctype==None:
                ctype="group"
                ctarget=useras.nick+"/group:default"
            else:
                ctarget=context['value']
            if ctype=="group":
                #below also does auth
                grp=self.whosdb.getGroup(currentuser, ctarget)
                authorize_context_member(False, self, currentuser, useras, grp)
                if userthere:
                    itemqset=itemqset.filter(pingrps__postfqin=ctarget, pingrps__postedby=useras.nick)
                else:
                    itemqset=itemqset.filter(pingrps__postfqin=ctarget)
            elif ctype=="app":
                app=self.whosdb.getApp(currentuser, ctarget)
                authorize_context_member(False, self, currentuser, useras, app)
                if userthere:
                    itemqset=itemqset.filter(pinapps__postfqin=ctarget, pingrps__postedby=useras.nick)
                else:
                    itemqset=itemqset.filter(pinapps__postfqin=ctarget)
            elif ctype=="library":
                libtag=self._getTag(currentuser, ctarget)
                authorize_context_member(False, self, currentuser, useras, libtag)
                if userthere:
                    itemqset=itemqset.filter(pinlibs__postfqin=ctarget, pinlibs__postedby=useras.nick)
                else:
                    itemqset=itemqset.filter(pinlibs__postfqin=ctarget)
            # elif ctype=="tag":
            #     datag=self._getTag(currentuser, ctarget)
            #     authorize_context_member(False, self, currentuser, useras, datag)
            #     if userthere:
            #         itemqset=itemqset.filter(stags__postfqin=ctarget, stags__postedby=useras.nick)
            #     else:
            #         itemqset=itemqset.filter(stags__postfqin=ctarget)
            else:
                itemqset=itemqset.filter(pingrps__postfqin=ctarget)
        else:
            print "NO CONTEXT"
            #you didnt ask for a group, or group AND user, or just user
            #what should we return? you are logged in
            #we could return a maximal set but will only return yours
            ctarget=useras.nick+"/group:default"
            itemqset=itemqset.filter(pingrps__postfqin=ctarget)

        #WHOA: what just happed. If you dont specify a context, a personal group context
        #will be handled down to you. Should we expand this?
        #also how do we handle counts?
        if sort:
            prefix=""
            if not sort['ascending']:
                prefix='-'
            sorter=prefix+sort['field']
            itemqset=itemqset.order_by(sorter)
        else:
            print "NO SORT"
        if shownfields:
            itemqset=itemqset.only(*shownfields)
        count=itemqset.count()

        if pagtuple:
            pagoffset=pagtuple[0]
            pagsize=pagtuple[1]
            if pagsize==None:
                pagsize=DEFPAGSIZE
            pagend=pagoffset+pagsize
            retset=itemqset[pagoffset:pagend]
        else:
            pagoffset=DEFPAGOFFSET
            pagsize=DEFPAGSIZE
            retset=itemqset

        return count, retset



    def getTagsForTagspec(self, currentuser, useras, criteria, context=None, sort=None):
        SHOWNFIELDS=['tagtype', 'singletonmode', 'basic.fqin', 'basic.description', 'basic.name', 'basic.uri', 'basic.creator', 'owner']
        klass=Tag
        result=self._makeQuery(klass, currentuser, useras, criteria, context, sort, SHOWNFIELDS, None)
        return result

    def getTagsByOwner(self, currentuser, useras, tagtype=None, context=None, singletonmode=False):
        criteria=[
            {'field':'owner', 'op':'eq', 'value':useras.nick},
            {'field':'singleton', 'op':'eq', 'value':singletonmode}
        ]
        if tagtype:
            criteria.append({'field':'tagtype', 'op':tagtype[0], 'value':tagtype[1]})
        result=getTagsForTagspec(self, currentuser, useras, criteria, context, sort)
        return result

    #You also have access to tags through group ownership of tags
    #no singletonmodes are usually transferred to group ownership
    #this will give me all
    def getTagsAsMemberAndOwner(self, currentuser, useras, tagtype=None, singletonmode=False, context=None, sort=None):
        criteria=[
            {'field':'members', 'op':'eq', 'value':useras.nick},
            {'field':'singleton', 'op':'eq', 'value':singletonmode}
        ]
        if tagtype:
            criteria.append({'field':'tagtype', 'op':tagtype[0], 'value':tagtype[1]})
        result=getTagsForTagspec(self, currentuser, useras, criteria, context, sort)
        return result

    #this is the stuff you get from group membership only
    def getTagsAsMemberOnly(self, currentuser, useras, tagtype=None, singletonmode=False, context=None, sort=None):
        criteria=[
            {'field':'owner', 'op':'ne', 'value':useras.nick},
            {'field':'members', 'op':'eq', 'value':useras.nick},
            {'field':'singleton', 'op':'eq', 'value':singletonmode}
        ]
        if tagtype:
            criteria.append({'field':'tagtype', 'op':tagtype[0], 'value':tagtype[1]})
        result=getTagsForTagspec(self, currentuser, useras, criteria, context, sort)
        return result

    def getItemsForItemspec(self, currentuser, useras, criteria, context=None, sort=None, pagtuple=None):
        SHOWNFIELDS=['itemtype', 'basic.fqin', 'basic.description', 'basic.name', 'basic.uri']
        klass=Item
        result=self._makeQuery(klass, currentuser, useras, criteria, context, sort, SHOWNFIELDS, pagtuple)
        return result

    #gets frpm groups, apps and libraries..ie items in them, not tags posted in them
    def getItemsForTagquery(self, currentuser, useras, query, context=None, sort=None, pagtuple=None):
        #tagquery is currently assumed to be a list of [{'tagtype', 'tagname'}]
        #we assume that
        tagquery=query.get("stags",[])
        libquery=query.get("libs",[])
        grpquery=query.get("groups",[])
        appquery=query.get("apps",[])
        criteria=[]
        for v in tagquery:
            criteria.append([
                {'field':'stags__tagname', 'op':'eq', 'value':v['tagname']},
                {'field':'stags__tagtype', 'op':'eq', 'value':v['tagtype']}
            ])
        for v in libquery:
            criteria.append([
                {'field':'pinlibs__tagname', 'op':'eq', 'value':v['libname']}
            ])
        for v in grpquery:
            criteria.append([
                {'field':'pingrps__postfqin', 'op':'eq', 'value':v['groupfqin']}
            ])
        for v in appquery:
            criteria.append([
                {'field':'pinapps__postfqin', 'op':'eq', 'value':v['appfqin']}
            ])
        result=getItemsForItemspec(self, currentuser, useras, criteria, context, sort, pagtuple)
        return result

    #one can use this to query the tag pingrps and pinapps
    #BUG we dont deal with stuff in the apps for now. Not sure
    #what that even means as apps are just copies.

    #filter taggings and postings by hand further if you want just your stuff
    #criteria exis to filter things down further, say by itemtype or tagtype
    #will be done on each item separately. Ditto for sort and pagetuple

    #BUG: not sure we handle libraries or tag ownership change correctly

    #run these without paginations to get everything we want.

    #BUG: in not enough, as we somehow separately need to get all the postings
    #consistent with the users access (array=individ item ok with eq
    #not other way around, and, well, in does or, but is that ok?)
    #BUG: no app access as yet

    def getTaggingsForSpec(self, currentuser, useras, itemfqinlist, criteria=[], context=None, sort=None, pagetuple=None):
        result={}
        groupsin=self.whosdb.groupsForUser(currentuser, useras)
        klass=TaggingDocument
        SHOWNFIELDS=[   'thething.postfqin',
                        'thething.thingtopostfqin',
                        'thething.thingtoposttype',
                        'thething.whenposted',
                        'thething.postedby',
                        'thething.tagtype',
                        'thething.tagname',
                        'thething.tagdescription']
        for fqin in itemfqinlist:
            criteria=[]
            #construct a query consistent with the users access
            #this includes the users personal group and the public group
            #should op be in?
            criteria.append([
                {'field':'pingrps__postfqin', 'op':'in', 'value':groupsin},
                {'field':'thething__thingtopostfqin', 'op':'eq', 'value':fqin}
            ])

            result[fqin]=self._makeQuery(klass, currentuser, useras, criteria, context, sort, pagetuple)
        return result

    def getPostingsForSpec(self, currentuser, useras, itemfqinlist, criteria=[], context=None, sort=None, pagetuple=None):
        result={}
        groupsin=self.whosdb.groupsForUser(currentuser, useras)
        SHOWNFIELDS=[   'thething.postfqin',
                        'thething.thingtopostfqin',
                        'thething.thingtoposttype',
                        'thething.whenposted',
                        'thething.postedby']

        klass=PostingDocument
        for fqin in itemfqinlist:
            criteria=[]
            #construct a query consistent with the users access
            #this includes the users personal group and the public group
            #should op be in?
            criteria.append([
                {'field':'thething__postfqin', 'op':'in', 'value':groupsin},
                {'field':'thething__thingtopostfqin', 'op':'eq', 'value':fqin}
            ])

            result[fqin]=self._makeQuery(klass, currentuser, useras, criteria, context, sort, pagetuple)
        return result

    #Now let us build other functions on the top of these



def initialize_application(sess):
    currentuser=None
    from whos import Whosdb
    whosdb=Whosdb(sess)
    postdb=Postdb(sess, whosdb)
    whosdb=postdb.whosdb
    adsgutuser=whosdb.getUserForNick(currentuser, "adsgut")
    adsuser=whosdb.getUserForNick(currentuser, "ads")
    #adsapp=whosdb.getApp(adsuser, "ads@adslabs.org/app:publications")
    currentuser=adsuser
    postdb.addItemType(currentuser, dict(name="pub", creator="ads", app="ads/app:publications"))
    postdb.addItemType(currentuser, dict(name="search", creator="ads", app="ads/app:publications"))
    postdb.addItemType(currentuser, dict(name="library", creator="ads", app="ads/app:publications"))
    postdb.addTagType(currentuser, dict(name="tag", creator="ads", app="ads/app:publications"))
    postdb.addTagType(currentuser, dict(name="library", creator="ads", app="ads/app:publications"))
    postdb.addTagType(currentuser, dict(name="note", creator="ads",
        app="ads/app:publications", tagmode=True, singletonmode=True))


def initialize_testing(db_session):
    from whos import Whosdb
    whosdb=Whosdb(db_session)
    postdb=Postdb(db_session, whosdb)

    currentuser=None
    adsuser=whosdb.getUserForNick(currentuser, "ads")
    currentuser=adsuser

    rahuldave=whosdb.getUserForNick(currentuser, "rahuldave")
    jayluker=whosdb.getUserForNick(currentuser, "jayluker")
    currentuser=rahuldave
    #postdb.saveItem(currentuser, rahuldave, dict(name="rahulbrary", itemtype="ads/library", creator=rahuldave.nick))
    postdb.makeTag(currentuser,rahuldave, dict(tagtype="ads/library", creator=rahuldave.nick, name="rahulbrary"))
    import simplejson as sj
    papers=sj.loads(open("file.json").read())
    currentuser=jayluker
    for k in papers.keys():
        paper={}
        paper['name']=papers[k]['bibcode']
        paper['creator']=jayluker.nick
        paper['itemtype']='ads/pub'
        print "========", paper
        postdb.saveItem(currentuser, jayluker, paper)
        print "paper", paper
        postdb.postItemIntoGroup(currentuser,jayluker, "rahuldave/group:ml", "ads/"+paper['basic'].name)

    #run this as rahuldave? Whats he point of useras then?
    currentuser=rahuldave
    postdb.saveItem(currentuser, rahuldave, dict(name="hello kitty", itemtype="ads/pub", creator=rahuldave.nick))
    #postdb.commit()
    postdb.saveItem(currentuser, rahuldave, dict(name="hello doggy", itemtype="ads/pub", creator=rahuldave.nick))
    postdb.saveItem(currentuser, rahuldave, dict(name="hello barkley", itemtype="ads/pub", creator=rahuldave.nick))
    postdb.saveItem(currentuser, rahuldave, dict(name="hello machka", itemtype="ads/pub", creator=rahuldave.nick))
    print "here"
    taggingdoc=postdb.tagItem(currentuser, rahuldave, "ads/hello kitty", dict(tagtype="ads/tag", creator=rahuldave.nick, name="stupid"))
    postdb.tagItem(currentuser, rahuldave, "ads/hello barkley", dict(tagtype="ads/tag", creator=rahuldave.nick, name="stupid"))
    print "W++++++++++++++++++"
    postdb.tagItem(currentuser, rahuldave, "ads/hello kitty", dict(tagtype="ads/tag", creator=rahuldave.nick, name="dumb"))
    postdb.tagItem(currentuser, rahuldave, "ads/hello doggy", dict(tagtype="ads/tag", creator=rahuldave.nick, name="dumb"))

    postdb.tagItem(currentuser, rahuldave, "ads/hello kitty", dict(tagtype="ads/note",
        creator=rahuldave.nick, name="somethingunique1", description="this is a note for the kitty", singletonmode=True))

    postdb.tagItem(currentuser, rahuldave, "ads/hello doggy", dict(tagtype="ads/tag", creator=rahuldave.nick, name="dumbdog"))
    postdb.tagItem(currentuser, rahuldave, "ads/hello doggy", dict(tagtype="ads/library", creator=rahuldave.nick, name="dumbdoglibrary"))
    postdb.tagItem(currentuser, rahuldave, "ads/hello kitty", dict(tagtype="ads/note",
        creator=rahuldave.nick, name="somethingunique2", description="this is a note for the doggy", singletonmode=True))

    print "LALALALALA"
    #Wen a tagging is posted to a group, the item should be autoposted into there too
    #NOTE: actually this is taken care of by posting into group on tagging, and making sure tags are posted
    #along with items into groups
    postdb.postItemIntoGroup(currentuser,rahuldave, "rahuldave/group:ml", "ads/hello kitty")
    postdb.postItemIntoGroup(currentuser,rahuldave, "adsgut/group:public", "ads/hello kitty")#public post
    postdb.postItemIntoGroup(currentuser,rahuldave, "rahuldave/group:ml", "ads/hello doggy")
    postdb.postItemIntoGroup(jayluker,jayluker, "rahuldave/group:ml", "ads/hello doggy")
    #TODO: below NOT NEEDED GOT FROM DEFAULT: SHOULD IT ERROR OUT GRACEFULLY OR BE IDEMPOTENT?
    postdb.postItemIntoApp(currentuser,rahuldave, "ads/app:publications", "ads/hello doggy")
    # print "PTGS"
    postdb.postTaggingIntoGroup(currentuser, rahuldave, "rahuldave/group:ml", taggingdoc)
    # print "1"
    # postdb.postTaggingIntoGroup(currentuser, rahuldave, "rahuldave@gmail.com/group:ml", "ads@adslabs.org/hello kitty", "rahuldave@gmail.com/ads@adslabs.org/tag:dumb")
    # postdb.postTaggingIntoGroup(currentuser, rahuldave, "rahuldave@gmail.com/group:ml", "ads@adslabs.org/hello doggy", "rahuldave@gmail.com/ads@adslabs.org/tag:dumbdog")
    # print "2"
    # #bottom commented as now autoadded
    # #postdb.postTaggingIntoApp(currentuser, rahuldave, "ads@adslabs.org/app:publications", "ads@adslabs.org/hello doggy", "rahuldave@gmail.com/ads@adslabs.org/tag:dumbdog")
    # print "HOOCH"
    # postdb.postTaggingIntoGroup(currentuser, rahuldave, "rahuldave@gmail.com/group:ml", "ads@adslabs.org/hello doggy", "rahuldave@gmail.com/ads@adslabs.org/tag2:dumbdog2")
    # #postdb.saveItem(currentuser, rahuldave, datadict)
    #
def test_gets(db_session):
    from whos import Whosdb
    whosdb=Whosdb(db_session)
    postdb=Postdb(db_session, whosdb)

    currentuser=None
    adsuser=whosdb.getUserForNick(currentuser, "ads")
    currentuser=adsuser

    rahuldave=whosdb.getUserForNick(currentuser, "rahuldave")
    currentuser=rahuldave
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave, 
        [[{'field':'basic__name', 'op':'eq', 'value':'hello kitty'}]])
    print "1++++", num, [v.basic.fqin for v in vals]
    #now disallowed as we removed the fallthrough
    # num, vals=postdb.getItemsForItemspec(currentuser, rahuldave, 
    #     [[{'field':'pingrps__postfqin', 'op':'eq', 'value':'rahuldave/group:ml'}]])
    # print "2++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave, 
        [[{'field':'stags__tagname', 'op':'eq', 'value':'stupid'}]])
    print "3++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave, 
        [[{'field':'pinlibs__tagname', 'op':'eq', 'value':'dumbdoglibrary'}]])
    print "4++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave, 
        [[{'field':'basic__name', 'op':'ne', 'value':'hello kitty'}]], 
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'})
    print "5++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave, 
        [[{'field':'basic__name', 'op':'ne', 'value':'hello kitty'}]], 
        {'user':True, 'type':'group', 'value':'rahuldave/group:ml'})
    print "6++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave,
        [[{'field':'basic__name', 'op':'ne', 'value':'hello kitty'}]],
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'},
        {'ascending':False, 'field':'basic__name'})
    print "7++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave,
        [[{'field':'basic__name', 'op':'ne', 'value':'hello kitty'}]],
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'},
        {'ascending':False, 'field':'basic__name'},
        (10, None))
    print "8++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(currentuser, rahuldave,
        [[{'field':'basic__name', 'op':'ne', 'value':'hello kitty'}]],
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'},
        {'ascending':False, 'field':'basic__name'},
        (5, 1))
    print "9++++", num, len(vals), vals, vals[0].to_json()
    # num, vals=postdb.getTaggingsForSpec(currentuser, rahuldave, 
    #     [[{'field':'thething__tagname', 'op':'eq', 'value':'stupid'}]])
    # print "++++", num, [v.to_json() for v in vals]

if __name__=="__main__":
    db_session=connect("adsgut")
    initialize_application(db_session)
    initialize_testing(db_session)
    test_gets(db_session)