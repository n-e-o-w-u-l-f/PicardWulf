"""Per-user Windows DPAPI secret storage, never Picard.ini/plaintext.

This module deliberately has NO insecure non-Windows persistent fallback.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

FIELDS=('spotify_client_id','spotify_client_secret','soundcloud_token','lastfm_api_key')


def credential_path():
    base=os.environ.get('LOCALAPPDATA')
    if not base:raise RuntimeError('LOCALAPPDATA unavailable; secret storage disabled')
    return Path(base)/'NEOWULF'/'Picard3'/'credentials.dpapi'


def _protect(data, decrypt=False):
    if os.name!='nt':raise RuntimeError('Windows DPAPI required; refusing plaintext secret storage')
    class BLOB(ctypes.Structure):
        _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    inp_buffer=ctypes.create_string_buffer(data)
    inp=BLOB(len(data),ctypes.cast(inp_buffer,ctypes.POINTER(ctypes.c_ubyte)))
    out=BLOB()
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.restype=wintypes.BOOL
    if decrypt:
        fn.argtypes=[ctypes.POINTER(BLOB),ctypes.c_void_p,ctypes.c_void_p,
                     ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(BLOB)]
        ok=fn(ctypes.byref(inp),None,None,None,None,0,ctypes.byref(out))
    else:
        fn.argtypes=[ctypes.POINTER(BLOB),wintypes.LPCWSTR,ctypes.c_void_p,
                     ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(BLOB)]
        ok=fn(ctypes.byref(inp),None,None,None,None,0,ctypes.byref(out))
    if not ok:raise OSError(ctypes.get_last_error(),'Windows DPAPI operation failed')
    try:return ctypes.string_at(out.pbData,out.cbData)
    finally:
        kernel.LocalFree.argtypes=[ctypes.c_void_p]
        kernel.LocalFree.restype=ctypes.c_void_p
        kernel.LocalFree(ctypes.cast(out.pbData,ctypes.c_void_p))


def load():
    if os.name!='nt':return {}
    p=credential_path()
    if not p.is_file():return {}
    if p.stat().st_size>65536:raise ValueError('Credential vault size invalid')
    obj=json.loads(_protect(p.read_bytes(),decrypt=True).decode('utf-8'))
    if not isinstance(obj,dict):raise ValueError('Credential vault invalid')
    return {k:v for k,v in obj.items() if k in FIELDS and isinstance(v,str)}


def save(values):
    if os.name!='nt':raise RuntimeError('Saving credentials requires Windows DPAPI')
    obj={k:v for k,v in values.items() if k in FIELDS and isinstance(v,str) and len(v)<=8192 and v}
    if not obj:raise ValueError('Refusing to store an empty vault')
    data=json.dumps(obj,ensure_ascii=False).encode('utf-8')
    p=credential_path();p.parent.mkdir(parents=True,exist_ok=True)
    encrypted=_protect(data)
    tmp=p.with_name(p.name+'.new-'+os.urandom(4).hex())
    try:
        with tmp.open('xb') as f:
            f.write(encrypted);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:tmp.unlink(missing_ok=True)
    return p
