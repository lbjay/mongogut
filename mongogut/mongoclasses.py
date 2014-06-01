from mongoengine import *
import datetime

#TODO: perhaps build in counters co collections
#membable-embedded->memberable-embedded; postable-embedded->membable-embedded

POSTABLES=[Library]#things that can be posted to
#Postables are both membable and ownable
MEMBERABLES=[Group, App, User]#things that can be members
MEMBERABLES_NOT_USER=[Group, App]
MEMBABLES=[Group, App, Library, Tag]#things you can be a member of
#above all use nicks
OWNABLES=[Group, App, Library, ItemType, TagType, Tag]#things that can be owned
#OWNERABLES=[Group, App, User]#things that can be owners. Do we need a shadow owner?
OWNERABLES=[User]
#The Memberable-Membable-Map tells you who can be a member of whom.
MMMAP={
    Group:{Group:False, App:False, User:True},
    App:{Group:True, App:False, User:True},
    Library:{Group:True, App:True, User:True},
    Tag:{Group:True, App:True, User:True}
}

#THIS NEEDS TO BE CHANGED. It has to refer to libraries
#The RWDEFMAP tells you about your membership mode. If you are a member of a group, it says u can read everything in
#the group and write to it, but for a library, you may read everything, but not necessarily write to it.
#(ie True maeans both read and write, false means read-only)
#i think App=True is a bug for now and we should use masquerading instead to get things into apps
#users ought not to add to apps directly.
RWDEFMAP={
    Group:True,
    App:True,#should apps use masquerading instead? BUG
    Library:False,
    Tag:False
}

#Should above be more detailed, such as below?
# #Critically, the fact that you cannot read all items in an app is done in _qproc
# #not sure that is right place.
# READDEFMAP={
#     Group:{Group:False, App:False, User:True},
#     App:{Group:False, App:False, User:True},
#     Library:{Group:False, App:False, User:True},
#     Tag:{Group:False, App:False, User:True}
# }
# WRITEDEFMAP={
#     Group:{Group:False, App:False, User:True},
#     App:{Group:False, App:False, User:True},
#     Library:{Group:False, App:False, User:True},
#     Tag:{Group:False, App:False, User:True}
# }

#Some notes

#(a) for reasons of historical accident, owner variables must be user fqin
#(earlier we wanted to allow groups/apps to own things)


#The BASIC interface: its utilized by almost everything else
class Basic(EmbeddedDocument):
  name = StringField(required=True)
  uri = StringField(default="", required=True)
  creator=StringField(required=True)
  whencreated=DateTimeField(required=True, default=datetime.datetime.now)
  lastmodified=DateTimeField(required=True, default=datetime.datetime.now)
  #Below is a combination of namespace and name
  fqin = StringField(required=True, unique=True)
  description = StringField(default="")

class ItemType(Document):
  classname="itemtype"
  basic = EmbeddedDocumentField(Basic)
  owner = StringField(required=True)#must be fqin of user
  postable = StringField(default="adsgut/adsgut", required=True)
  postabletype = StringField(required=True)

class TagType(Document):
  classname="tagtype"
  basic = EmbeddedDocumentField(Basic)
  owner = StringField(required=True)#must be fqin of user
  postable = StringField(required=True)
  postabletype = StringField(required=True)
  #Document tagmode 0/1 here
  tagmode = StringField(default='0', required=True)
  #singleton mode, if true, means that a new instance of this tag must be created each time
  #once again example is note, which is created with a uuid as name
  singletonmode = BooleanField(default=False, required=True)

#We are calling it PostablEmbedded, but this is now a misnomer. We might change this name.
#This is anything that "CAN HAVE" a member. ie the memberable interface
class MembableEmbedded(EmbeddedDocument):
  fqpn = StringField(required=True)
  ptype = StringField(required=True)
  pname = StringField(required=True)
  owner = StringField(required=True)#must be fqin of user
  readwrite = BooleanField(required=True, default=False)
  description = StringField(default="")

#The MemberableEmbedded represents a unit that is a member (MEMBER-IN), for example a user,
#group or app that is member of a library or tag, or a user or group that is member
#of an app, or a user who is a member of a group

class MemberableEmbedded(EmbeddedDocument):
  fqmn = StringField(required=True)
  mtype = StringField(required=True)
  pname = StringField(required=True)
  readwrite = BooleanField(required=True, default=False)

def Gget_member_fqins(memb):
    return [ele.fqmn for ele in memb.members]

def Gget_member_pnames(memb):
    return [ele.pname for ele in memb.users]

def Gget_member_rws(memb):
    perms={}
    for ele in memb.members:
        perms[ele.fqmn]=[ele.pname, ele.readwrite]
    return perms

def Gget_invited_fqins(memb):
    return [ele.fqmn for ele in memb.inviteds]

def Gget_invited_pnames(memb):
    return [ele.pname for ele in memb.inviteds]

def Gget_invited_rws(memb):
    perms={}
    for ele in memb.inviteds:
        perms[ele.fqmn]=[ele.pname, ele.readwrite]
    return perms


class Tag(Document):
  classname="tag"
  meta = {
      'indexes': ['owner', 'basic.name', 'tagtype','basic.whencreated'],
      'ordering': ['-basic.whencreated']
  }
  basic = EmbeddedDocumentField(Basic)
  tagtype = StringField(required=True)
  singletonmode = BooleanField(required=True)#default is false but must come from tagtype
  #The owner of a tag can be a user, group, or app
  #This is different from creator as ownership can be transferred. You
  #see this in groups and apps too. Its like a duck.
  owner = StringField(required=True)
  #Seems like this was needed for change ownership

  #@interface=MEMBERS
  members = ListField(EmbeddedDocumentField(MemberableEmbedded))
  inviteds = ListField(EmbeddedDocumentField(MemberableEmbedded))

  #METHODS
  def presentable_name(self):
      return self.basic.name

  def get_member_fqins(self):
      return Gget_member_fqins(self)

  def get_member_pnames(memb):
      return Gget_member_pnames(memb)

  def get_member_rws(self):
      return Gget_member_rws(self)

  def get_invited_fqins(self):
      return Gget_invited_fqins(self)

  def get_invited_pnames(memb):
      return Gget_invited_pnames(memb)

  def get_invited_rws(self):
      return Gget_invited_rws(self)




class User(Document):
    "the adsgut user object in mongodn. distinct from the giovanni user object"
    classname="user"
    meta = {
      'indexes': ['nick', 'basic.name', 'adsid', 'basic.whencreated'],
      'ordering': ['-basic.whencreated']
    }
    adsid = StringField(required=True, unique=True)
    cookieid = StringField(required=True, unique=True)
    classicimported = BooleanField(default=False, required=True)
    #Unless user sets nick, its equal to adsid

    #@interface=BASIC
    nick = StringField(required=True, unique=True)
    basic = EmbeddedDocumentField(Basic)

    #@interface=MEMBERSHIP-IN (augmented by owned)
    #note the postables is now a misnomer, it is anything you
    #can be a member in
    postablesin=ListField(EmbeddedDocumentField(MembableEmbedded))
    postablesowned=ListField(EmbeddedDocumentField(MembableEmbedded))
    postablesinvitedto=ListField(EmbeddedDocumentField(MembableEmbedded))

    def membableslibrary(self, pathinclude_p=False):
        "get a list of libraries for user, with indirect membership included"
        plist=[]
        libs=[]
        lfqpns=[]
        pathincludes=defaultdict(list)
        #first get the libraries etc we are directly members of
        for ele in self.postablesin:
            if ele.ptype == 'library':
                libs.append(ele)
                lfqpns.append(ele.fqpn)
                pathincludes[ele.fqpn].append((ele.ptype, ele.pname, ele.fqpn))
        #TODO:the below is removed for an array. Any code which depends on this in the JS should be changed.
        # for l in lfqpns:
        #     pathincludes[l] = ""
        #ok now lets target the non-directs
        for ele in self.postablesin:
            if ele.ptype != 'library':
                p = MAPDICT[ele.ptype].objects(basic__fqin=ele.fqpn).get()
                #this is a group or app so get the postables it is in
                ls = p.postablesin
                for e in ls:
                    #dont pick up anything else than libraries that the groups and apps are in
                    if e.ptype=='library':
                        pathincludes[e.fqpn].append((ele.ptype, ele.pname, ele.fqpn))
                        plist.append(e)
        #put all the libraries together. there might be dupes
        libs = libs + plist
        pdict={}
        rw={}
        for l in libs:
            #this does the set like behaviour so that we have the library only once
            if not pdict.has_key(l.fqpn):
                pdict[l.fqpn] = l
                rw[l.fqpn] = l.readwrite
            else:
                #this ensures that we get the most permissive permission of the library
                rw[l.fqpn] = rw[l.fqpn] or l.readwrite

        #This is a hack. We never save in mongodb so to be cheap we just overwrite the reference we saved
        #to the library with the most general read-write
        for k in pdict.keys():
            pdict[k].readwrite = rw[k]

        #see if we want dictionary as well as values.
        if pathinclude_p:
            return pdict.values(), pathincludes
        else:
            return pdict.values()

    def membablesnotlibrary(self):
        plist=[]
        for ele in self.postablesin:
          if ele.ptype != 'library':
              plist.append(ele)
        return plist


    def presentable_name(self):
        return self.adsid

#POSTABLES
class Group(Document):
    classname="group"
    meta = {
        'indexes': ['owner', 'basic.name', 'nick','basic.whencreated'],
        'ordering': ['-basic.whencreated']
    }

    #DEPRECATED: it has now become a personal library
    personalgroup=BooleanField(default=False, required=True)

    #@interface=BASIC
    nick = StringField(required=True, unique=True)
    basic = EmbeddedDocumentField(Basic)
    owner = StringField(required=True)

    #@interface=MEMBERS
    members = ListField(EmbeddedDocumentField(MemberableEmbedded))
    inviteds = ListField(EmbeddedDocumentField(MemberableEmbedded))#only fqmn

    #@interface=MEMBERSHIP-IN
    postablesin=ListField(EmbeddedDocumentField(MembableEmbedded))

    def get_member_fqins(self):
        return Gget_member_fqins(self)

    def get_member_pnames(memb):
        return Gget_member_pnames(memb)

    def get_member_rws(self):
        return Gget_member_rws(self)

    def get_invited_fqins(self):
        return Gget_invited_fqins(self)

    def get_invited_pnames(memb):
        return Gget_invited_pnames(memb)

    def get_invited_rws(self):
        return Gget_invited_rws(self)

    def get_postablesin_rws(self):
        perms={}
        for ele in self.postablesin:
            perms[ele.fqpn]=[ele.pname, ele.readwrite]
        return perms

    def presentable_name(self, withoutclass=False):
        if withoutclass:
            return self.basic.name
        return self.classname+":"+self.basic.name

class App(Document):
    classname="app"
    meta = {
        'indexes': ['owner', 'basic.name', 'nick', 'basic.whencreated'],
        'ordering': ['-basic.whencreated']
    }

    #@interface=BASIC
    nick = StringField(required=True, unique=True)
    basic = EmbeddedDocumentField(Basic)
    owner = StringField(required=True)

    #@interface=MEMBERS
    members = ListField(EmbeddedDocumentField(MemberableEmbedded))
    inviteds = ListField(EmbeddedDocumentField(MemberableEmbedded))

    #@interface=MEMBERSHIP-IN
    postablesin=ListField(EmbeddedDocumentField(MembableEmbedded))


    def get_member_fqins(self):
        return Gget_member_fqins(self)

    def get_member_pnames(memb):
        return Gget_member_pnames(memb)

    def get_member_rws(self):
        return Gget_member_rws(self)

    def get_invited_fqins(self):
        return Gget_invited_fqins(self)

    def get_invited_pnames(memb):
        return Gget_invited_pnames(memb)

    def get_invited_rws(self):
        return Gget_invited_rws(self)

    def get_postablesin_rws(self):
        perms={}
        for ele in self.postablesin:
            perms[ele.fqpn]=[ele.pname, ele.readwrite]
        return perms

    def presentable_name(self, withoutclass=False):
        if withoutclass:
            return self.basic.name
        return self.classname+":"+self.basic.name

class Library(Document):
    classname="library"
    meta = {
        'indexes': ['owner', 'basic.name', 'nick', 'basic.whencreated'],
        'ordering': ['-basic.whencreated']
    }

    #@interface=BASIC
    nick = StringField(required=True, unique=True)
    basic = EmbeddedDocumentField(Basic)
    owner = StringField(required=True)

    #Two NEW fields added to library
    #this one can be "udg" (1 per user), "public" (1), "group" (1 per group), "app"(1 per app)
    librarykind = StringField(required=False, default="library")
    #did you make the library public? (public group and anonymouse support)
    #QUESTION: should it be public library (post or not), and anonymouse separate? I think so.
    islibrarypublic = BooleanField(default=False, required=False)

    #@interface=MEMBERS
    members = ListField(EmbeddedDocumentField(MemberableEmbedded))
    inviteds = ListField(EmbeddedDocumentField(MemberableEmbedded))


    def get_member_fqins(self):
        return Gget_member_fqins(self)

    def get_member_pnames(memb):
        return Gget_member_pnames(memb)

    def get_member_rws(self):
        return Gget_member_rws(self)

    def get_invited_fqins(self):
        return Gget_invited_fqins(self)

    def get_invited_pnames(memb):
        return Gget_invited_pnames(memb)

    def get_invited_rws(self):
        return Gget_invited_rws(self)


    def presentable_name(self, withoutclass=False):
        if withoutclass:
            return self.basic.name
        return self.classname+":"+self.basic.name

#
#POSTING AND TAGGING ARE DUCKS. A tagging is a kind-of post
#
class Post(EmbeddedDocument):

    meta = {'allow_inheritance':True}
    #this would be the fqin of the tag too.
    postfqin=StringField(required=True)
    posttype=StringField(required=True)
    #below is the item and itemtype
    thingtopostfqin=StringField(required=True)
    thingtoposttype=StringField(required=True)
    whenposted=DateTimeField(required=True, default=datetime.datetime.now)
    postedby=StringField(required=True)

class Tagging(Post):
    tagtype=StringField(default="ads/tag", required=True)
    tagname=StringField(required=True)
    tagdescription=StringField(default="", required=True)
    tagmode = StringField(default='0', required=True)
    singletonmode = BooleanField(default=False, required=True)


class PostingDocument(Document):
    classname="postingdocument"
    meta = {
        'indexes': ['posting.postfqin', 'posting.posttype', 'posting.whenposted', 'posting.postedby', 'posting.thingtoposttype', 'posting.thingtopostfqin', ('posting.postfqin', 'posting.thingtopostfqin')],
        'ordering': ['-posting.whenposted']
    }
    posting=EmbeddedDocumentField(Post)

class TaggingDocument(Document):
    classname="taggingdocument"
    meta = {
        'indexes': ['posting.postfqin', 'posting.posttype', 'posting.whenposted', 'posting.postedby', 'posting.thingtoposttype', 'posting.tagname', 'posting.tagtype', 'posting.thingtopostfqin', ('posting.postfqin', 'posting.thingtopostfqin')],
        'ordering': ['-posting.whenposted']
    }
    posting=EmbeddedDocumentField(Tagging)
    #In which libraries has this tagging has been posted
    pinpostables = ListField(EmbeddedDocumentField(Post))


#how to have indexes work within pinpostables abd stags? use those documents
#hopefully we are doing this but how to handle the multiple postings?
class Item(Document):
    classname="item"
    meta = {
        'indexes': ['itemtype', 'basic.whencreated', 'basic.name'],
        'ordering': ['-basic.whencreated']
    }
    #itypefqin
    itemtype = StringField(required=True)
    basic = EmbeddedDocumentField(Basic)
    #In which libraries have we been posted?
    pinpostables = ListField(EmbeddedDocumentField(Post))
    #What tags have been applied to these items?
    stags = ListField(EmbeddedDocumentField(Tagging))


MAPDICT={
    'group':Group,
    'app':App,
    'user':User,
    'library':Library
}

if __name__=="__main__":
    pass
