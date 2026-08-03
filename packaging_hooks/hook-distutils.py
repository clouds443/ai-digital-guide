# -*- coding: utf-8 -*-
try:
    import sysconfig

    try:
        hiddenimports = [sysconfig._get_sysconfigdata_name()]
    except TypeError:
        hiddenimports = [sysconfig._get_sysconfigdata_name(True)]
except Exception:
    hiddenimports = []
