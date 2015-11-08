import carddav2
import vobject
import requests
import lxml.etree as ET
import sqlite3
import os
import glib
import settings
import threading
import time
import Queue
import sys


def sync_local_changes(pycarddav, sqlConn, addressbook=None):
    # sync new vcards to the server
    for href,etag,vcard in sqlConn.execute('select href,etag,vcard from vcards where local_status=1').fetchall():
        (href_new, etag_new) = pycarddav.upload_new_card(vcard)
        print("Synced a locally new vcard to the server with new href %s and etag %s" % (href_new, etag_new))
        if addressbook: addressbook.update_from_sync(href, href_new, etag_new)
        sqlConn.execute('update vcards set etag=?,href=?,local_status=0 where href=?', (etag_new,href_new,href))

    # sync locally deleted vcards to the server
    for href,etag in sqlConn.execute('select href,etag from vcards where local_status=2').fetchall():
        pycarddav.delete_vcard(href,etag)
        print("Delete a local deletion to the server with href %s" % href)
        sqlConn.execute('delete from vcards where href=?', (href,))

    # sync locally modified vcards to the server
    for href,etag,vcard in sqlConn.execute('select href,etag,vcard from vcards where local_status=3').fetchall():
        etag_new = pycarddav.update_vcard(vcard, href, etag)
        print("Synced a locally modified vcard to the server with the new etag %s" % etag_new)
        if addressbook: addressbook.update_from_sync(href, href, etag_new)
        sqlConn.execute('update vcards set etag=?,local_status=0 where href=?', (etag_new,href))


def write_to_vcf(sqlConn, filepath):
    file = open(filepath, 'w')
    for (vcard,) in sqlConn.execute('select vcard from vcards where local_status<>2').fetchall():
        file.write(vcard.encode('UTF-8'))
        file.write('\n')


def full_sync(addressbook=None):
    my_settings = settings.get_settings()
    if my_settings['resource'] == "":
        return

    # sqlite3 database connection
    conn = sqlite3.connect(os.path.join(glib.get_user_config_dir(), 'pyaddressbook', 'addressbook.db'))

    # local_status 0=nothing, 1=locally new, 2=locally deleted, 3=locally modified
    conn.execute('CREATE TABLE if not exists vcards (etag text primary key unique  not null, href text unique not null, vcard text not null, local_status smallint default 0)')
    conn.commit()

    available_href2etag = {}
    for href,etag in conn.execute('select href,etag from vcards where local_status<>1').fetchall():
        available_href2etag[href] = etag

    cdav = carddav2.PyCardDAV(verify=my_settings['verify'], resource=my_settings['resource'], user=my_settings['user'], passwd=my_settings['passwd'], write_support=True)
    abook = cdav.get_abook()

    deleted_vcards = available_href2etag.copy()
    server_modified_vcards = {}

    for href,etag in abook.items():
        if href in deleted_vcards:
            del deleted_vcards[href]
        if not href in available_href2etag or available_href2etag[href] != etag:
            server_modified_vcards[href] = etag

    # delete local vcards if they have been removed from the server side
    for href,etag in deleted_vcards.items():
        print("Removing contact for href: %s" % href)
        conn.execute('delete from vcards where href=?', (href,))
        if addressbook: addressbook.vcard_removed(href)


    # update local vcards that have been modified on the server side (regardless of the local status, i.e. locally modified vcards will be updated to the server side version)
    href_list = [ href for href,etag in server_modified_vcards.items() ]
    if len(href_list) > 0:
        print('Requesting modified/new vcards from server')
        dav_list = cdav._get_vcards(href_list)
        for dav in dav_list:
            href = dav['href']
            status = dav['status']
            etag = dav['etag']
            vcard = dav['vcard']
            print("Updating vcard for href %s since it was updated on the server-side" % href)
            if href in available_href2etag:
                conn.execute('update vcards set etag=?,href=?,vcard=?,local_status=0 where href=?', (etag,href,vcard,href))
                if addressbook: addressbook.vcard_updated(href, vcard)
            else:
                conn.execute('INSERT INTO vcards VALUES (?,?,?,0)', (etag,href, vcard))
                if addressbook: addressbook.vcard_added(href, etag, vcard)

    sync_local_changes(cdav, conn)
    if my_settings['write_vcf']:
        write_to_vcf(conn, my_settings['vcf_path'])

    conn.commit()
    conn.close()


def SyncerThread(queue, addressbook):
    while True:
        item = queue.get()
        if item == 'sync_local_changes':
            try:
                my_settings = settings.get_settings()
                if my_settings['resource'] != '':
                    sqlConn = sqlite3.connect(os.path.join(glib.get_user_config_dir(), 'pyaddressbook', 'addressbook.db'))
                    cdav = carddav2.PyCardDAV(verify=my_settings['verify'], resource=my_settings['resource'], user=my_settings['user'], passwd=my_settings['passwd'], write_support=True)
                    sync_local_changes(cdav, sqlConn, addressbook)
                    sqlConn.commit()
                    sqlConn.close()
            except:
                print("Error occured while trying to sync changes. Exception details:\n", sys.exc_info())
        if item == 'full_sync':
            try:
                print("Starting a full sync")
                full_sync(addressbook)
            except:
                print("Error occured while trying to do a full sync. Exception details:\n", sys.exc_info())

        queue.task_done()
        if item == "STOP": break
