#!/usr/bin/env python

from distutils.core import setup,Command

setup(name='Addressbook',
      version='0.2',
      description='PyGTK Addressbook',
      author='Andreas Fink',
      author_email='andreas.fink85@gmail.com',
      url='',
      license='GPLv3',
      packages=['addressbook'],
      scripts=['pyaddressbook'],
      data_files=[('share/pyaddressbook', ['addressbook/edit_dialog.glade', 'addressbook/export_dialog.glade', 'addressbook/settings_dialog.glade'])],
      requires=['pygtk', 'vobject']
     )
