"""签收正文摘要工具：复验时统一按同一套规则规范化文本并计算校验值。

历史签收摘要是在签收当时对正文算出来的，复验必须使用完全相同的规范化规则，
否则同样的文字会因为换行、行首空白或空白行不同而算出不同的摘要。
"""
from __future__ import annotations

import hashlib
import string


def canonical_text(text: str | None) -> str:
    """规范化正文：统一换行、去掉每行首尾空白、丢弃空行后按行拼接。"""
    if not text:
        return ""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line)


def text_digest(text: str | None) -> str:
    """返回规范化正文的完整 MD5 摘要（32 位小写十六进制）。"""
    return hashlib.md5(canonical_text(text).encode("utf-8")).hexdigest()


def normalize_digest(value: str | None) -> str:
    """规范化用户提交的摘要：去前缀、空格、连字符并转小写。"""
    digest = str(value or "").strip().lower()
    if digest.startswith("md5:"):
        digest = digest[4:]
    return digest.replace(" ", "").replace("-", "")


def digest_equivalent(left: str | None, right: str | None) -> bool:
    """比较两个摘要。

    正常情况下完整 32 位摘要必须完全一致；为兼容历史界面展示的 8 位截断
    摘要，当较短一方是 8 位及以上十六进制前缀时也视为同一摘要。
    """
    a, b = normalize_digest(left), normalize_digest(right)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = sorted((a, b), key=len)
    if len(short) < 8 or any(char not in string.hexdigits.lower() for char in short):
        return False
    return long.startswith(short)
