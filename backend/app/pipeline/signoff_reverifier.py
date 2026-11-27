"""签收正文复验器：按历史包号核对签收当时的正文。

核心行为：
- 已签收字幕包只按签收当时的 V1 归档正文复验，V2 及后续版本不参与判断
- 提交的签收摘要必须等于签收当时记录的原摘要
- 手中字幕的规范化摘要必须同时等于原摘要和 V1 归档正文摘要
- 复验未通过时不得产出正式引用
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.digest import digest_equivalent, normalize_digest, text_digest


@dataclass(frozen=True)
class ArchivedVersionBody:
    """归档的版本文本：签收当时的正文快照，落库后不再改写。"""

    version_id: str
    version_no: str
    body: str
    digest: str
    archived_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "version_no": self.version_no,
            "body": self.body,
            "digest": self.digest,
            "archived_at": self.archived_at,
        }


class SignoffArchive:
    """签收正文归档：按版本号保存签收当时的正文，正文只读。"""

    def __init__(self) -> None:
        self._bodies: dict[str, ArchivedVersionBody] = {}

    def archive(
        self, version_id: str, version_no: str, body: str, archived_at: str = "",
    ) -> ArchivedVersionBody:
        """归档一份版本文本；同一版本号重复归档视为冲突，保持首次落库的正文。"""
        key = self._key(version_no)
        if key in self._bodies:
            return self._bodies[key]
        entry = ArchivedVersionBody(
            version_id=version_id,
            version_no=version_no,
            body=body,
            digest=text_digest(body),
            archived_at=archived_at,
        )
        self._bodies[key] = entry
        return entry

    @staticmethod
    def _key(version_no: str) -> str:
        text = str(version_no or "").strip().lower()
        if text.startswith("v"):
            text = text[1:]
        return text

    def get(self, version_id: str) -> ArchivedVersionBody | None:
        for entry in self._bodies.values():
            if entry.version_id == version_id:
                return entry
        return None

    def get_by_version_no(self, version_no: str) -> ArchivedVersionBody | None:
        return self._bodies.get(self._key(version_no))

    def snapshot(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._bodies.values()]


@dataclass
class SignoffPack:
    """历史签收包：记录签收当时的版本、原摘要、接收人与引用状态。"""

    pack_id: str
    media_id: str
    version_id: str
    version_no: str
    signoff_digest: str
    receiver: str
    signed_at: str

    def version_is_v1(self) -> bool:
        return SignoffArchive._key(self.version_no) == "1"


@dataclass
class ReverifyOutcome:
    """一次复验的判定结果。"""

    ok: bool
    code: str
    message: str
    submitted_digest: str = ""
    computed_digest: str = ""
    archived_digest: str = ""
    next_handler: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "通过" if self.ok else "不通过"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "code": self.code,
            "message": self.message,
            "submitted_digest": self.submitted_digest,
            "computed_digest": self.computed_digest,
            "archived_digest": self.archived_digest,
            "next_handler": self.next_handler,
            "notes": list(self.notes),
        }


class SignoffReverifier:
    """复验器：只认签收当时的 V1 正文与原签收摘要。"""

    def verify(
        self,
        pack: SignoffPack,
        archive: SignoffArchive,
        submitted_digest: str,
        subtitles: str,
    ) -> ReverifyOutcome:
        """执行复验；任一项不满足都不得产出正式引用。"""
        submitted = normalize_digest(submitted_digest)
        computed = text_digest(subtitles)
        receiver = pack.receiver or "签收接收人"
        retry_hint = f"接收人 {receiver}：补报有效的原签收摘要及字幕"

        # 1. 只允许按签收当时的 V1 正文复验，V2 及后续版本不得参与判断。
        if not pack.version_is_v1():
            return ReverifyOutcome(
                ok=False,
                code="VERSION_NOT_V1",
                message=(
                    f"字幕包 {pack.pack_id} 的签收版本为 {pack.version_no}，"
                    "复验只按签收当时的 V1 正文验证，V2 及后续版本不参与判断"
                ),
                submitted_digest=submitted,
                computed_digest=computed,
                next_handler="版本管理员：按 V1 签收记录重新登记后再复验",
            )

        archived = archive.get_by_version_no("v1")
        if archived is None:
            return ReverifyOutcome(
                ok=False,
                code="BODY_NOT_ARCHIVED",
                message=f"字幕包 {pack.pack_id} 签收当时的 V1 正文未归档，无法复验",
                submitted_digest=submitted,
                computed_digest=computed,
                next_handler="归档管理员：补齐签收当时的 V1 正文",
            )

        if not str(subtitles or "").strip():
            return ReverifyOutcome(
                ok=False,
                code="SUBTITLES_MISSING",
                message="未提交手中字幕正文，服务端无法计算实际校验",
                submitted_digest=submitted,
                computed_digest=computed,
                archived_digest=archived.digest,
                next_handler=retry_hint,
            )

        # 2. 手中字幕必须是 V1 正文。拿到 V2 正文时明确拒绝，绝不让 V2 参与判断。
        normalised_archived = normalize_digest(archived.digest)
        if not digest_equivalent(computed, normalised_archived):
            v2 = archive.get_by_version_no("v2")
            if v2 is not None and digest_equivalent(computed, v2.digest):
                message = (
                    f"手中字幕是 V2 正文，与字幕包 {pack.pack_id} 签收当时的 V1 正文不符；"
                    "V2 不参与签收正文判断，不能生成正式引用"
                )
                code = "VERSION_V2_REJECTED"
            else:
                message = (
                    f"手中字幕与字幕包 {pack.pack_id} 签收当时的 V1 归档正文不符，"
                    "不能生成正式引用"
                )
                code = "SUBTITLES_NOT_V1"
            return ReverifyOutcome(
                ok=False,
                code=code,
                message=message,
                submitted_digest=submitted,
                computed_digest=computed,
                archived_digest=archived.digest,
                next_handler=retry_hint,
            )

        # 3. 提交的摘要必须是签收当时记录的原摘要。
        if not submitted:
            return ReverifyOutcome(
                ok=False,
                code="DIGEST_MISSING",
                message="未提交原签收摘要，无法与签收记录核对",
                submitted_digest="",
                computed_digest=computed,
                archived_digest=archived.digest,
                next_handler=retry_hint,
            )
        if not digest_equivalent(submitted, pack.signoff_digest):
            return ReverifyOutcome(
                ok=False,
                code="DIGEST_MISMATCH",
                message=(
                    f"提交的签收摘要与字幕包 {pack.pack_id} 的历史签收摘要不符，"
                    "不能生成正式引用"
                ),
                submitted_digest=submitted,
                computed_digest=computed,
                archived_digest=archived.digest,
                next_handler=retry_hint,
            )

        # 4. 原摘要还必须与 V1 归档正文一致：文字相同但签收摘要不符的旧包挡在这里。
        if not digest_equivalent(submitted, normalised_archived):
            return ReverifyOutcome(
                ok=False,
                code="SIGNOFF_DIGEST_INCONSISTENT",
                message=(
                    f"字幕包 {pack.pack_id} 的原签收摘要与 V1 归档正文不一致，"
                    "该旧包不能生成有效引用"
                ),
                submitted_digest=submitted,
                computed_digest=computed,
                archived_digest=archived.digest,
                next_handler=retry_hint,
            )

        return ReverifyOutcome(
            ok=True,
            code="VERIFIED",
            message=f"复验通过：手中字幕与字幕包 {pack.pack_id} 签收当时的 V1 正文一致",
            submitted_digest=submitted,
            computed_digest=computed,
            archived_digest=archived.digest,
            next_handler="无需办理（正式引用已补全）",
        )
