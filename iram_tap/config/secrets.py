"""Windows DPAPI: credentials are usable only by the current Windows user."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise ValueError("API 키 보관은 Windows에서 지원됩니다.")
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1,
                    ctypes.byref(destination)):
        raise ValueError("API 키 암호화/복호화 실패. 이 Windows 계정에서 키를 다시 저장하세요.")
    try:
        return ctypes.string_at(destination.data, destination.size)
    finally:
        kernel32.LocalFree(destination.data)


def protect_key(key: str) -> str:
    return base64.b64encode(_crypt(key.encode("utf-8"), decrypt=False)).decode("ascii")


def unprotect_key(value: str) -> str:
    if not value:
        raise ValueError("설정의 Fish Audio 탭에서 API 키를 저장하세요.")
    try:
        return _crypt(base64.b64decode(value, validate=True), decrypt=True).decode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise ValueError("API 키를 읽을 수 없습니다. 설정에서 키를 다시 저장하세요.") from error
