import json
from os import path
import glib

def_settings = { 'resource': '',
                  'user': '',
                  'passwd': '',
                  'verify': True,
                  'write_vcf': True,
                  'vcf_path': path.join(glib.get_user_config_dir(), 'pyaddressbook', 'addressbook.vcf')
               }
settings_path = path.join(glib.get_user_config_dir(), 'pyaddressbook', 'config')

def get_settings():
    settings = def_settings.copy()
    try:
        settings.update(json.load(open(settings_path, 'r')))
    except:
        pass
    return settings


def save_settings(settings):
    new_settings = get_settings()
    new_settings.update(settings)
    json.dump(settings, open(settings_path, 'w'))
