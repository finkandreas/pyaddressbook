import vobject
from os import path
import sys


formatted_name_order = ('prefix', 'given', 'additional', 'family', 'suffix')
adr_order = ('street', 'city', 'region', 'code', 'country', 'box', 'extended')
defined_types = dict( { 'email': ('home', 'work'),
                        'adr': ('home', 'work'),
                        'tel': ('home', 'work', 'voice', 'text', 'fax', 'cell', 'video', 'pager', 'textphone') } )
month_strings = ( 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec' )

def find_glade_dir():
  # 1. alternative: install_prefix/share/pyaddressbook/glade
  # 2. alternative: source_directory
  alternative_dirs = ( path.join(path.dirname(sys.argv[0]), path.pardir, 'share', 'pyaddressbook'),
                       path.dirname(__file__)
                     )
  for p in alternative_dirs:
    if path.exists( path.join(p, 'edit_dialog.glade') ):
      return p


glade_dir = find_glade_dir()


class cis(object):
  def __init__(self, s):
    self.s = s
  def __cmp__(self, other):
    return cmp(self.s.lower(), other.lower())
  def __eq__(self, other):
    return self.s.lower() == other.lower()


def vcard21_to_vcard30(vcard):
  for attr in ('adr_list', 'tel_list', 'email_list'):
    if hasattr(vcard, attr):
      for  val in getattr(vcard, attr):
        if 'TYPE' not in val.params:
          val.params['TYPE'] = val.singletonparams
          val.singletonparams = []
  vcard.version.value = "3.0"


def vcard30_to_vcard40(vcard):
  for attr in ('adr_list','tel_list', 'email_list'):
    if hasattr(vcard, attr):
      for val in getattr(vcard, attr):
        if 'TYPE' in val.params:
          if cis('pref') in val.params['TYPE']:
            val.params['TYPE'].remove(cis('PREF'))
            val.params['PREF'] = ['1']
          if val.params['TYPE'] == []:
            del val.params['TYPE']
  for attr in ('n_list', 'fn_list', 'adr_list'):
    if hasattr(vcard, attr):
      for val in getattr(vcard, attr):
        val.params['CHARSET'] = ['UTF-8']
  vcard.version.value = '4.0'


def create_formatted_name(vcard):
  name = vcard.getChildValue('n', None)
  fn = ' '.join( getattr(name, val) for val in formatted_name_order )
  return fn.lstrip().rstrip().replace('  ', ' ').replace('  ', ' ')


def vcard_get_pref_value(vcard_entry):
  return int(vcard_entry.params['PREF'][0]) if hasattr(vcard_entry, 'pref_param') else 101


def create_type_pref_string(vcard_entry, brackets=False ):
  if brackets:
    ret = ' ('+','.join(vcard_entry.type_paramlist).lower()+')' if hasattr(vcard_entry, 'type_paramlist') else ''
  else:
    ret = ','.join(vcard_entry.type_paramlist).lower() if hasattr(vcard_entry, 'type_paramlist') else ''
  ret += '['+str(vcard_entry.pref_param)+']' if hasattr(vcard_entry, 'pref_param') else ''
  return ret
