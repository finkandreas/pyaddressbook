import vobject
import gtk
import gobject
import glib
import copy
from signal import *
from dateutil.parser import parse
from dateutil.rrule import rrule,YEARLY
from datetime import datetime
from misc import *
from edit_dialog import EditDialog
from os import path,makedirs
from shutil import move
import re
import sys
import sqlite3
import uuid
import settings
import sync
import threading
import Queue


class Addressbook(gtk.Window):
  def __init__(self, sqlFilepath, parent=None):
    gtk.Window.__init__(self)
    try:
      self.set_screen(parent.get_screen())
    except AttributeError:
      self.connect('destroy', lambda *w: gtk.main_quit())
    self.set_title('Addressbook')
    icon_theme = gtk.icon_theme_get_default()
    icon = icon_theme.load_icon('stock_new-address-book', 48, 0)
    self.set_icon(icon)
    gtk.window_set_default_icon(icon)

    hbox = gtk.HBox(False, 8)
    self.add(hbox)

    button_hbox = gtk.HButtonBox()
    button_hbox.set_layout(gtk.BUTTONBOX_START)
    button_hbox.set_spacing(8)
    add_button = gtk.Button('_Add', gtk.STOCK_ADD)
    edit_button = gtk.Button('_Edit', gtk.STOCK_EDIT)
    del_button = gtk.Button('_Delete', gtk.STOCK_DELETE)
    import_button = gtk.Button('_Import vCard')
    import_button.set_image( gtk.image_new_from_pixbuf(gtk.icon_theme_get_default().load_icon('vcard', gtk.ICON_SIZE_BUTTON, 0)) )
    export_button = gtk.Button('_Export vCard')
    export_button.set_image( gtk.image_new_from_pixbuf(gtk.icon_theme_get_default().load_icon('vcard', gtk.ICON_SIZE_BUTTON, 0)) )
    settings_button = gtk.Button('_Synchronisation settings')
    settings_button.set_image( gtk.image_new_from_pixbuf(gtk.icon_theme_get_default().load_icon('stock_properties', gtk.ICON_SIZE_BUTTON, 0)) )
    button_hbox.pack_start(add_button)
    button_hbox.pack_start(edit_button)
    button_hbox.pack_start(del_button)
    button_hbox.pack_start(import_button)
    button_hbox.pack_start(export_button)
    button_hbox.pack_start(settings_button)
    add_button.connect('clicked', self.add_contact)
    edit_button.connect('clicked', self.edit_contact)
    del_button.connect('clicked', self.delete_contact)
    import_button.connect('clicked', self.import_file)
    export_button.connect('clicked', self.export_file)
    settings_button.connect('clicked', self.open_settings)

    vbox = gtk.VBox(False, 0)
    sw = gtk.ScrolledWindow()
    sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    vbox.pack_start(sw, True, True, 2)
    vbox.pack_end(button_hbox, False, False, 8)
    hbox.pack_start(vbox, True, True, 2)

    # idx in card_list, formatted name, email, bday, next_bday_diff (for sorting), tel
    self.model = gtk.ListStore( gobject.TYPE_INT, gobject.TYPE_STRING, gobject.TYPE_STRING,
                                gobject.TYPE_STRING, gobject.TYPE_LONG, gobject.TYPE_STRING )
    self.treeview = gtk.TreeView(self.model)
    self.treeview.set_rules_hint(True)
    self.treeview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
    sw.add(self.treeview)
    column = gtk.TreeViewColumn('Name', gtk.CellRendererText(), text=1)
    column.set_resizable(True)
    column.set_sort_column_id(1)
    self.treeview.append_column(column)
    column = gtk.TreeViewColumn('Email', gtk.CellRendererText(), text=2)
    column.set_resizable(True)
    column.set_sort_column_id(2)
    self.treeview.append_column(column)
    column = gtk.TreeViewColumn('Birthday', gtk.CellRendererText(), text=3)
    column.set_resizable(True)
    column.set_sort_column_id(4)
    self.treeview.append_column(column)
    column = gtk.TreeViewColumn('Telephone', gtk.CellRendererText(), text=5)
    column.set_resizable(True)
    column.set_sort_column_id(5)
    self.treeview.append_column(column)
    self.treeview.get_selection().connect('changed', self.on_selection_changed)
    self.treeview.connect('row_activated', self.on_row_activated)

    self.vcard_label = gtk.Label()
    self.vcard_label.set_selectable(True)
    hbox.pack_end(self.vcard_label, False, False, 2)

    self.card_list_sql = {}
    self.key_from_href = {}
    self.max_key = 0
    self.sqlFilepath = sqlFilepath
    self.read_contacts_from_db(self.sqlFilepath)
    self.treeview.get_column(0).clicked()
    self.show_all()
    self.maximize()

    gobject.threads_init()
    self.syncerThreadQueue = Queue.Queue()
    self.syncerThreadQueue.put('full_sync')
    self.syncerThread = threading.Thread(target=sync.SyncerThread, kwargs={"queue": self.syncerThreadQueue, "addressbook": self})
    self.syncerThread.start()

    gtk.quit_add(0, self.stopSyncerThread)

    for sig in (SIGINT, SIGTERM):
      signal(sig, gtk.main_quit)


  def stopSyncerThread(self):
    self.syncerThreadQueue.put("STOP")
    self.syncerThread.join()

  def update_treeview_values(self, card, treeview_iter):
    name = card.getChildValue('fn', '')
    email = card.getChildValue('email', '')
    tel = card.getChildValue('tel', '')
    bday = ''
    bday_diff = 400 # more than 1 year for ppl without a bday ;)
    if hasattr(card, 'bday'):
      bday_string = card.bday.value
      bday_datetime = parse(bday_string).replace(tzinfo=None)
      bday = '%02d.%02d.%04d' % (bday_datetime.day, bday_datetime.month, bday_datetime.year)
      next_bday_rule = rrule(YEARLY, bymonth=bday_datetime.month, bymonthday=bday_datetime.day)
      td = next_bday_rule.after(bday_datetime, True) - datetime.today()
      bday_diff = td.days
    self.model.set(treeview_iter, 1, name, 2, email, 3, bday, 4, bday_diff, 5, tel)


  def on_selection_changed(self, selection):
    sel = selection.get_selected_rows()
    if sel[1]:
      (href,etag,vcard,local_status) = self.card_list_sql[ sel[0].get_value( sel[0].get_iter(sel[1][0]), 0 ) ]
      vcard_formatted = 'Name: ' + vcard.getChildValue('fn', '') + '\n'
      vcard_formatted += 'Full name: ' + create_formatted_name(vcard) + '\n\n'
      if hasattr(vcard, 'bday'):
        d = parse(vcard.bday.value).replace(tzinfo=None)
        vcard_formatted += 'Birthday: ' + '%02d %s %04d'%(d.day, month_strings[d.month-1], d.year) + '\n\n'
      if hasattr(vcard, 'email_list'):
        for email in vcard.email_list:
          vcard_formatted += 'Email' + create_type_pref_string(email, True) + ':\n\t' + email.value + '\n'
        vcard_formatted += '\n'
      if hasattr(vcard, 'adr_list'):
        for adr in vcard.adr_list:
          vcard_formatted += 'Address' + create_type_pref_string(adr, True) + ':\n\t' + adr.value.street + '\n\t'  + adr.value.code + ' ' + adr.value.city + '\n\t' + adr.value.country + '\n\n'
      if hasattr(vcard, 'tel_list'):
        for tel in vcard.tel_list:
          vcard_formatted += 'Telephone' + create_type_pref_string(tel, True) + ':\n\t' + tel.value + '\n'
        vcard_formatted += '\n'
      self.vcard_label.set_text( vcard_formatted )


  def on_row_activated(self, treeview, path, view_column):
    self.edit_contact()


  def add_contact(self, button=None):
    self.max_key += 1
    vcard = vobject.vCard()
    vcard.add( 'fn' )
    vcard.add( 'n' )
    vcard.add( 'version' )
    vcard.version.value = '3.0'
    d = EditDialog(vcard, self)
    if d.run() == gtk.RESPONSE_ACCEPT:
      conn = sqlite3.connect(self.sqlFilepath)
      href = str(uuid.uuid4())
      conn.execute('INSERT INTO vcards VALUES (?,?,?,1)', (href,href,unicode(d.get_vcard().serialize())))
      conn.commit()
      conn.close()
      self.card_list_sql[self.max_key] = (href,href,d.get_vcard(),1)
      treeiter = self.model.append( (self.max_key, '', '', '', 400, '') )
      self.key_from_href[href] = (self.max_key, treeiter)
      self.syncerThreadQueue.put('sync_local_changes')
      self.update_treeview_values(vcard, treeiter)
      self.treeview.get_selection().select_iter(treeiter)
    d.destroy()


  def edit_contact(self, button=None):
    sel = self.treeview.get_selection().get_selected_rows()
    if sel[1]:
      (href,etag,vcard,local_status) = self.card_list_sql[sel[0].get_value( sel[0].get_iter(sel[1][0]), 0 )]
      vcard_copy = copy.deepcopy(vcard)
      edit_dialog = EditDialog(vcard_copy, self)
      if edit_dialog.run() == gtk.RESPONSE_ACCEPT:
        treeiter = sel[0].get_iter(sel[1][0])
        idx = self.model.get_value( treeiter, 0 )
        conn = sqlite3.connect(self.sqlFilepath)
        local_status = 3 if local_status != 1 else 1
        conn.execute('update vcards set vcard=?,local_status=? where href=?', (unicode(edit_dialog.get_vcard().serialize()), local_status, href))
        conn.commit()
        conn.close()
        self.card_list_sql[idx] = (href,etag,edit_dialog.get_vcard(),local_status)
        self.syncerThreadQueue.put('sync_local_changes')
        self.update_treeview_values( edit_dialog.get_vcard(), treeiter )
        self.on_selection_changed(self.treeview.get_selection())
      edit_dialog.destroy()


  def delete_contact(self, button=None):
    sel = self.treeview.get_selection().get_selected_rows()
    if sel[1]:
      iter = sel[0].get_iter(sel[1][0])
      key = self.model.get_value(iter, 0)
      idx = self.model.get_path(iter)[0];
      self.treeview.get_selection().select_path( idx+1 if len(self.card_list_sql) != idx+1 else idx-1 )
      (href,etag,vcard,local_status) = self.card_list_sql[key]
      conn = sqlite3.connect(self.sqlFilepath)
      if local_status == 1:
          conn.execute('delete from vcards where href=?', (href,))
      else:
          conn.execute('update vcards set local_status=2 where href=?', (href,))
      conn.commit()
      conn.close()
      del self.card_list_sql[key]
      self.syncerThreadQueue.put('sync_local_changes')
      self.model.remove(iter)


  def read_contacts_from_db(self, sqlFilepath, convert=False, sort=False):
    conn = sqlite3.connect(sqlFilepath)
    conn.execute('CREATE TABLE if not exists vcards (etag text primary key unique  not null, href text unique not null, vcard text not null, local_status smallint default 0)')
    conn.commit()
    for self.max_key,(href,etag,vcard,local_status) in enumerate(conn.execute('select href,etag,vcard,local_status from vcards where local_status<>2').fetchall(), self.max_key):
      card = vobject.readOne(vcard)
      if not hasattr(card, 'fn'):
        card.add('fn')
      if not hasattr(card, 'n'):
        card.add('n')
      if not hasattr(card, 'version'):
        card.add('version')
        card.version.value = "2.1"
      if convert:
        if card.version.value == "2.1":
          vcard21_to_vcard30(card)
        if card.version.value != "3.0":
          raise exception.NotImplementedError
      if sort:
        for val in ('tel_list', 'email_list', 'adr_list'):
          if hasattr(card,val):
            getattr(card, val).sort(key=vcard_get_pref_value)

      # TODO: remove the next line(s)
      if hasattr(card, 'label'): print(card.label.value)

      iter = self.model.append( (self.max_key, '', '', '', 400, '') )
      self.update_treeview_values(card, iter)
      self.card_list_sql[self.max_key] = (href,etag,card,local_status)
      self.key_from_href[href] = (self.max_key, iter)


  def import_file(self, button):
    d = gtk.FileChooserDialog('Choose vCard', self, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    d.set_select_multiple( True )
    file_filter = gtk.FileFilter()
    file_filter.set_name('vCard files')
    file_filter.add_pattern('*.vcf')
    d.add_filter(file_filter)
    file_filter = gtk.FileFilter()
    file_filter.set_name('All files')
    file_filter.add_pattern('*')
    d.add_filter(file_filter)
    if d.run() == gtk.RESPONSE_ACCEPT:
      for filename in d.get_filenames():
        self.max_key += 1
        try:
          cards = vobject.readComponents( open(filename, 'r').read() )
          conn = sqlite3.connect(self.sqlFilepath)
          for self.max_key, card in enumerate(cards, self.max_key):
            if not hasattr(card, 'fn'):
              card.add('fn')
            if not hasattr(card, 'n'):
              card.add('n')
            if not hasattr(card, 'version'):
              card.add('version')
              card.version.value = "2.1"
            if card.version.value == "2.1":
              vcard21_to_vcard30(card)
            if card.version.value != "3.0":
              raise exception.NotImplementedError

            for val in ('tel_list', 'email_list', 'adr_list'):
              if hasattr(card,val):
                getattr(card, val).sort(key=vcard_get_pref_value)

            href = str(uuid.uuid4())
            conn.execute('INSERT INTO vcards VALUES (?,?,?,1)', (href,href,unicode(card.serialize())))
            self.card_list_sql[self.max_key] = (href,href,card,1)
            iter = self.model.append( (self.max_key, '', '', '', 400, '') )
            self.key_from_href[href] = (self.max_key, iter)
            self.update_treeview_values(card, iter)
          conn.commit()
          conn.close()
          self.syncerThreadQueue.put('sync_local_changes')
        except IOError:
          print 'WARNING: Error while opening file',filename
    d.destroy()


  def export_file(self, button):
    builder = gtk.Builder()
    builder.add_from_file( path.join(glade_dir, 'export_dialog.glade') )
    d = builder.get_object('export_dialog')
    d.set_transient_for(self)
    builder.get_object('path_search_button').connect('clicked', self.search_export_path, builder.get_object('path_entry'))
    if d.run() == gtk.RESPONSE_ACCEPT:
      export_list = None
      if builder.get_object('export_all_button').get_active():
        export_list = [ item[2] for item in self.card_list_sql.values() ]
      else:
        sel = self.treeview.get_selection().get_selected_rows()
        export_list = [ self.card_list_sql[sel[0].get_value(sel[0].get_iter(k), 0)][2] for k in sel[1] ]
      for i, card in enumerate(export_list):
        f = open( path.join(builder.get_object('path_entry').get_text(), str(i)+'.vcf'), 'w' )
        s = card.serialize(lineLength=1000)
        regexp = re.compile(r'TYPE=(.*?)[;:]')
        matches = regexp.findall(s)
        for m in matches:
          replace = m.replace(',', ';TYPE=')
          s=s.replace(m, replace)
        f.write( s )
        f.write( '\n' )
    d.destroy()


  def search_export_path(self, button, entry):
    d = gtk.FileChooserDialog('Choose vcard', self, gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT) )
    if d.run() == gtk.RESPONSE_ACCEPT:
      entry.set_text(d.get_filename())
    d.destroy()


  def open_settings(self, button):
    builder = gtk.Builder()
    builder.add_from_file( path.join(glade_dir, 'settings_dialog.glade') )
    d = builder.get_object('settings_dialog')
    builder.get_object('vcf_path_search_button').connect('clicked', self.search_export_path, builder.get_object('vcf_path_entry'))
    d.set_transient_for(self)
    my_settings = settings.get_settings()
    for e in ['resource', 'user', 'passwd', 'vcf_path']: builder.get_object(e+'_entry').set_text(my_settings[e])
    for e in ['verify', 'write_vcf']: builder.get_object(e+'_checkbutton').set_active(my_settings[e])
    if d.run() == gtk.RESPONSE_ACCEPT:
      new_settings = {}
      for e in ['resource', 'user', 'passwd', 'vcf_path']: new_settings[e] = builder.get_object(e+'_entry').get_text()
      for e in ['verify', 'write_vcf']: new_settings[e] = builder.get_object(e+'_checkbutton').get_active()
      settings.save_settings(new_settings)
    d.destroy()
    self.syncerThreadQueue.put('full_sync')


  def update_from_sync(self, href, href_new, etag_new):
    (key,iter) = self.key_from_href[href]
    (href_old, etag_old, vcard, local_status) = self.card_list_sql[key]
    self.card_list_sql[key] = (href_new, etag_new, vcard, 0)
    del self.key_from_href[href]
    self.key_from_href[href_new] = (key, iter)


  def vcard_removed(self, href):
    if href in self.key_from_href:
      (key,iter) = self.key_from_href[href]
      del self.key_from_href[href]
      del self.card_list_sql[key]
      self.model.remove(iter)



  def vcard_updated(self, href, vcard):
    if href in self.key_from_href:
      (key,iter) = self.key_from_href[href]
      vcard = vobject.readOne(vcard)
      self.update_treeview_values(vcard, iter)
      (href, etag, _, _) = self.card_list_sql[key]
      self.card_list_sql[key] = (href, etag, vcard, 0)

  def vcard_added(self, href, etag, vcard):
    self.max_key += 1
    vcard = vobject.readOne(vcard)
    self.card_list_sql[self.max_key] = (href,etag,vcard,0)
    treeiter = self.model.append( (self.max_key, '', '', '', 400, '') )
    self.key_from_href[href] = (self.max_key, treeiter)
    self.update_treeview_values(vcard, treeiter)
