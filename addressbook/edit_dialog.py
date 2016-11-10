import gtk
import gobject
from dateutil.parser import parse
from datetime import datetime
from misc import *

class EditDialog(gtk.Dialog):
  def __init__(self, vcard, parent=None):
    title = "Editing " + vcard.getChildValue('fn', '...')
    gtk.Dialog.__init__(self, title, parent, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                        (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    self.builder = gtk.Builder()
    self.builder.add_from_file( path.join(glade_dir, 'edit_dialog.glade') )
    self.vbox.pack_start(self.builder.get_object('tab_widget'))
    self.vcard = vcard

    for val in formatted_name_order:
      self.builder.get_object(val+'_entry').set_text(getattr(vcard.n.value, val))
      self.builder.get_object(val+'_entry').connect('changed', self.update_formatted_name)
    self.builder.get_object('formatted_name_entry').set_text(vcard.fn.value)
    if hasattr(vcard, 'bday'):
      d = parse(vcard.bday.value, dayfirst=True).replace(tzinfo=None)
      self.builder.get_object('birthday_entry').set_text( '%02d.%02d.%04d' % (d.day, d.month, d.year) )
    self.builder.get_object('fn_autoupdate_button').set_active(vcard.fn.value == create_formatted_name(vcard))
    self.builder.get_object('birthday_button').connect('clicked', self.show_birthday_calendar)
    self.builder.get_object('fn_autoupdate_button').connect('clicked', self.update_formatted_name)

    self.adr_type_combobox = gtk.combo_box_new_text()
    self.builder.get_object('adr_type_box').pack_start(self.adr_type_combobox)
    self.builder.get_object('adr_type_box').child_set_property(self.adr_type_combobox, 'position', 0)
    self.adr_type_combobox.show()
    self.cur_address_index = -1
    if hasattr(vcard, 'adr_list'):
      vcard.adr_list.sort(key=vcard_get_pref_value)
      for adr in vcard.adr_list:
        self.adr_type_combobox.append_text( create_type_pref_string(adr) )
    self.adr_type_combobox.connect('changed', self.adr_type_changed)
    self.adr_type_combobox.set_active(0)
    self.adr_tab_update()
    self.builder.get_object('adr_add_button').connect('clicked', self.add_address)
    self.builder.get_object('adr_edit_type_button').connect('clicked', self.edit_address_type)
    self.builder.get_object('adr_del_button').connect('clicked', self.del_address)

    self.tel_email_entries = []
    self.build_tel_email_tab()

    self.type_chooser_dialog = gtk.Dialog("Choose type...", self, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    self.type_chooser_dialog.vbox.pack_start(self.builder.get_object('type_chooser_table'))


  def get_vcard(self):
    self.adr_writeback()
    self.tel_email_writeback()
    for val in formatted_name_order:
      setattr( self.vcard.n.value, val, self.builder.get_object(val+'_entry').get_text() )
    self.vcard.fn.value = self.builder.get_object('formatted_name_entry').get_text()
    if hasattr(self.vcard, 'bday'):
      del self.vcard.bday
    d = parse(self.builder.get_object('birthday_entry').get_text(), default=datetime(1, 2, 3), dayfirst=True )
    if d != datetime(1, 2, 3):
      self.vcard.add('bday').value = '%04d-%02d-%02d' % (d.year, d.month, d.day)
    #ugly hack to remove the label from the address field
    if hasattr(self.vcard, 'label'): del self.vcard.label # This is an ugly hack, but it is useful since android shows the label instead of the updated address
    if hasattr(self.vcard, 'adr_list'):
      for adr in self.vcard.adr_list:
        if hasattr(adr, "label_paramlist"): del adr.label_paramlist
    return self.vcard


  def build_tel_email_tab(self):
    self.tel_email_writeback()
    max_tel_table_columns = 4
    tel_table = self.builder.get_object('tel_table')
    tel_table.foreach(tel_table.remove)
    prefix = ('Tel', 'Email')
    k = 0
    self.tel_email_entries = []
    for j, attr in enumerate( ('tel_list', 'email_list') ):
      if hasattr(self.vcard, attr):
        getattr(self.vcard, attr).sort(key=vcard_get_pref_value)
        for i, val in enumerate(getattr(self.vcard, attr)):
          l = gtk.Label( prefix[j]+ ( create_type_pref_string(val, brackets=True)+':') )
          l.set_property('xalign', 0)
          e = gtk.Entry()
          e.set_text( val.value )
          edit_type_button = gtk.Button()
          edit_type_button.set_image( gtk.image_new_from_stock(gtk.STOCK_EDIT, gtk.ICON_SIZE_MENU) )
          del_button = gtk.Button()
          del_button.set_image( gtk.image_new_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_MENU) )
          user_param = ( attr, i, l, e )
          edit_type_button.connect('clicked', self.edit_tel_email, user_param)
          del_button.connect('clicked', self.del_tel_email, user_param)
          tel_table.attach(l, 0, 1, k, k+1, xoptions=gtk.FILL, yoptions=0)
          tel_table.attach(e, 1, 2, k, k+1, yoptions=0)
          tel_table.attach(edit_type_button, 2, 3, k, k+1, 0, 0)
          tel_table.attach(del_button, 3, 4, k, k+1, 0, 0)
          self.tel_email_entries.append( (e, val) )
          k += 1
    add_tel_button = gtk.Button( label='Add phone number' )
    add_tel_button.set_image(gtk.image_new_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_BUTTON))
    add_email_button = gtk.Button( label='Add email' )
    add_email_button.set_image(gtk.image_new_from_stock(gtk.STOCK_ADD, gtk.ICON_SIZE_BUTTON))
    add_tel_button.connect('clicked', self.add_tel_email, 'tel' )
    add_email_button.connect('clicked', self.add_tel_email, 'email' )
    add_tel_button.set_property('yalign', 1)
    add_email_button.set_property('yalign', 1)
    button_box = gtk.HButtonBox()
    button_box.set_spacing(10)
    button_box.pack_start(add_tel_button)
    button_box.pack_start(add_email_button)
    alignment = gtk.Alignment(yalign=1)
    tel_table.attach(alignment, 0, max_tel_table_columns, k, k+1)
    alignment.add(button_box)
    tel_table.show_all()


  def update_formatted_name(self, obj):
    if self.builder.get_object('fn_autoupdate_button').get_active():
      fn = ''
      for val in formatted_name_order:
        fn += self.builder.get_object(val+'_entry').get_text() + ' '
      self.builder.get_object('formatted_name_entry').set_text(fn.lstrip().rstrip().replace('  ', ' ').replace('  ', ' '))


  def show_birthday_calendar(self, button):
    date = parse(self.builder.get_object('birthday_entry').get_text(), dayfirst=True)
    dialog = gtk.Dialog("Choose birthday...", self, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                       (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    calendar = gtk.Calendar()
    calendar.select_month(date.month-1, date.year)
    calendar.select_day(date.day)
    calendar.show()
    dialog.vbox.pack_start(calendar)
    dialog.set_position( gtk.WIN_POS_MOUSE )
    if dialog.run() == gtk.RESPONSE_ACCEPT:
      d = calendar.get_date()
      self.builder.get_object('birthday_entry').set_text( '%02d.%02d.%04d' % (d[2], d[1]+1, d[0]) )
    dialog.destroy()


  def adr_type_changed(self, combobox):
    self.adr_writeback()
    self.cur_address_index = combobox.get_active()
    if hasattr(self.vcard, 'adr_list') and combobox.get_active() != -1 and combobox.get_active() < len(self.vcard.adr_list):
      adr = self.vcard.adr_list[combobox.get_active()].value
      for val in adr_order:
        self.builder.get_object(val+'_entry').set_text(getattr(adr, val))
    self.adr_tab_update()


  def adr_writeback(self):
    if self.cur_address_index != -1:
      adr = self.vcard.adr_list[self.cur_address_index].value
      for val in adr_order:
        setattr(adr, val, self.builder.get_object(val+'_entry').get_text())


  def adr_tab_update(self):
    state = True if self.cur_address_index != -1 else False
    self.builder.get_object('adr_edit_type_button').set_sensitive( state )
    self.builder.get_object('adr_del_button').set_sensitive( state )
    for val in adr_order:
      self.builder.get_object(val+'_entry').set_sensitive( state )


  def add_address(self, obj):
    adr = vobject.newFromBehavior('ADR')
    if self.set_type_and_preferred(vcard_key='adr', vcard_entry=adr):
      self.vcard.add( adr )
      adr.value = vobject.vcard.Address()
      adr.isNative = True
      adr.params['CHARSET'] = ['UTF-8']
      self.adr_type_combobox.append_text( create_type_pref_string(adr) )
      self.adr_type_combobox.set_active( len(self.vcard.adr_list)-1 )


  def edit_address_type(self, obj):
    adr = self.vcard.adr_list[self.adr_type_combobox.get_active()]
    if self.set_type_and_preferred(vcard_entry=adr, vcard_key='adr'):
      self.adr_type_combobox.get_model().set_value( self.adr_type_combobox.get_active_iter(), 0, create_type_pref_string(adr) )


  def set_type_and_preferred(self, vcard_entry, vcard_key):
    initial_type_list = [ s.lower() for s in vcard_entry.type_paramlist ] if hasattr(vcard_entry, 'type_param') else []
    button_box = self.builder.get_object('type_chooser_buttonbox')
    button_box.foreach( button_box.remove )
    type_buttons = list()
    for t in defined_types[vcard_key]:
      button = gtk.CheckButton( label=t )
      button_box.pack_start( button )
      type_buttons.append( button )
      if t in initial_type_list:
        button.set_active( True )
        initial_type_list.remove(t)
    self.builder.get_object('type_chooser_entry').set_text(','.join(initial_type_list))
    self.builder.get_object('preferred_spin').set_value(float(vcard_entry.pref_param) if hasattr(vcard_entry, 'pref_param') else 0)
    self.type_chooser_dialog.vbox.show_all()
    response = self.type_chooser_dialog.run()
    if response == gtk.RESPONSE_ACCEPT:
      selected_types = [b.get_label() for b in type_buttons if b.get_active()]
      if self.builder.get_object('type_chooser_entry').get_text() != '':
        selected_types.extend( self.builder.get_object('type_chooser_entry').get_text().split(',') )
      if len(selected_types) > 0:
        vcard_entry.params['TYPE'] = selected_types
      elif hasattr(vcard_entry, 'type_param'):
        del vcard_entry.params['TYPE']
      if self.builder.get_object('preferred_spin').get_value_as_int() != 0:
        vcard_entry.params['PREF'] = [str(self.builder.get_object('preferred_spin').get_value_as_int())]
      elif hasattr(vcard_entry, 'pref_param'):
        del vcard_entry.params['PREF']
    self.type_chooser_dialog.hide()
    return response == gtk.RESPONSE_ACCEPT


  def del_address(self, obj):
    if self.cur_address_index != -1:
      idx = self.cur_address_index
      self.cur_address_index = -1   # set to -1 for no address write-back when combobx changed signal is emitted
      del self.vcard.adr_list[ idx ]
      self.adr_type_combobox.remove_text( idx )
      for val in adr_order:
        self.builder.get_object(val+'_entry').set_text('')
      self.adr_type_combobox.set_active( 0 )


  def add_tel_email(self, button, user_param):
    # user_param = vcard_attr
    self.vcard.add(user_param)
    tel_email = getattr(self.vcard, user_param+'_list')[-1]
    if self.set_type_and_preferred(vcard_entry=tel_email, vcard_key=user_param):
      self.build_tel_email_tab()
    else:
      del getattr(self.vcard, user_param+'_list')[-1]


  def edit_tel_email(self, button, user_param):
    # user_param = (vcard_attr, index in vcard_attr list, label in gui, entry in gui)
    tel_email = getattr(self.vcard, user_param[0])[ user_param[1] ]
    vcard_key = user_param[0].replace('_list', '')
    if self.set_type_and_preferred(vcard_key=vcard_key, vcard_entry=tel_email):
      self.build_tel_email_tab()

  def del_tel_email(self, button, user_param):
    # user_param = (vcard_attr, index in vcard_attr list, label in gui, entry in gui)
    del getattr(self.vcard, user_param[0])[ user_param[1] ]
    self.build_tel_email_tab()


  def tel_email_writeback(self):
    for val in self.tel_email_entries:
      tel_email = val[1]
      val[1].value = val[0].get_text()
