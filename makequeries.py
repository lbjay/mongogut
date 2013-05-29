from classes import *
import itemsandtags

def test_gets(db_session):
    BIBCODE='2004A&A...418..625D'
    currentuser=None
    postdb=itemsandtags.Postdb(db_session)
    whosdb=postdb.whosdb

    print "getting adsgutuser"
    adsgutuser=whosdb.getUserForNick(currentuser, "adsgut")
    print "getting adsuser"
    adsuser=whosdb.getUserForNick(adsgutuser, "ads")
    currentuser=adsuser

    rahuldave=whosdb.getUserForNick(adsgutuser, "rahuldave")
    jayluker=whosdb.getUserForNick(adsgutuser, "jayluker")
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [[{'field':'basic__name', 'op':'eq', 'value':BIBCODE}]])
    print "1++++", num, [v.basic.fqin for v in vals], vals[0].to_json()
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [[{'field':'pinpostables__postfqin', 'op':'eq', 'value':'rahuldave/group:ml'}]])
    print "2++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [{'pinpostables':[{'field':'postfqin', 'op':'eq', 'value':'rahuldave/group:ml'}]}])
    print "2b++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [],
        {'user':True, 'type':'group', 'value':'rahuldave/group:ml'})
    print "3++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(jayluker, jayluker, 
        [],
        {'user':True, 'type':'group', 'value':'rahuldave/group:ml'})
    print "3b++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(adsuser, adsuser, 
        [],
        {'user':False, 'type':'app', 'value':'ads/app:publications'})
    print "APPPPPPP++++", num, [v.basic.fqin for v in vals]
    #BUG: we are currently not able to AND something in criteria with the context. Its one or the other
    #for this we also need a no context!=users default context mode.
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [], 
        {'user':True, 'type':'library', 'value':'rahuldave/library:mll'})
    print "4++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [[{'field':'basic__name', 'op':'ne', 'value':BIBCODE}]], 
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'})
    print "5++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave, 
        [[{'field':'basic__name', 'op':'ne', 'value':BIBCODE}]], 
        {'user':True, 'type':'group', 'value':'rahuldave/group:ml'})
    print "6++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave,
        [[{'field':'basic__name', 'op':'ne', 'value':BIBCODE}]],
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'},
        {'ascending':False, 'field':'basic__name'})
    print "7++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave,
        [[{'field':'basic__name', 'op':'ne', 'value':BIBCODE}]],
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'},
        {'ascending':False, 'field':'basic__name'},
        (10, None))
    print "8++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForItemspec(rahuldave, rahuldave,
        [[{'field':'basic__name', 'op':'ne', 'value':BIBCODE}]],
        {'user':False, 'type':'group', 'value':'rahuldave/group:ml'},
        {'ascending':False, 'field':'basic__name'},
        (5, 1))
    print "9++++", num, len(vals), vals, vals[0].to_json()

def test_item_query(db_session):
    currentuser=None
    postdb=itemsandtags.Postdb(db_session)
    whosdb=postdb.whosdb

    print "getting adsgutuser"
    adsgutuser=whosdb.getUserForNick(currentuser, "adsgut")
    print "getting adsuser"
    adsuser=whosdb.getUserForNick(adsgutuser, "ads")
    currentuser=adsuser

    rahuldave=whosdb.getUserForNick(adsgutuser, "rahuldave")
    jayluker=whosdb.getUserForNick(adsgutuser, "jayluker")
    num, vals=postdb.getItemsForQuery(rahuldave, rahuldave,
       {'postables':["rahuldave/library:mll"]} )
    print "1++++", num, [v.basic.fqin for v in vals]
    #BUG:below errors ouit
    num, vals=postdb.getItemsForQuery(rahuldave, rahuldave,
       {'stags':['rahuldave/ads/tagtype:tag:boring'],'postables':["rahuldave/group:ml", "jayluker/group:sp"]} )
    print "2++++", num, [v.basic.fqin for v in vals]
    num, vals=postdb.getItemsForQuery(rahuldave, rahuldave,
       {'postables':["rahuldave/group:ml"]} , 
       {'user':True, 'type':'user', 'value':'adsgut/user:rahuldave'})
    print "3++++", num, [v.basic.fqin for v in vals]

if __name__=="__main__":
    db_session=connect("adsgut")
    test_gets(db_session)
    test_item_query(db_session)
    #libs_in_grps
    #tagtypetag_takeovers