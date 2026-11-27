"""签收正文复验领域服务：按历史包号复验签收正文并补全版本引用。

业务流程：
- 字幕包签收后，签收当时的 V1 正文归档，但正式引用可能写入中断
- 接收人在复验页提交包号、原签收摘要与手中字幕，服务端计算实际校验
- 复验通过才补写正式引用并同步转写版本被引用次数
- 每次复验的归档凭据永久追加保留，未确认引用始终显示为「引用中断（未确认）」
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.pipeline.signoff_fixtures import (
    ARCHIVED_BODIES,
    HISTORICAL_PACKS,
    V1_DIGEST,
)
from app.pipeline.signoff_reverifier import (
    ReverifyOutcome,
    SignoffArchive,
    SignoffPack,
    SignoffReverifier,
)
from app.services.base import BaseModuleService
from app.store import store

UNCONFIRMED_STATE = "引用中断（未确认）"
CONFIRMED_STATE = "已确认（正式引用）"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SignoffReverifyService(BaseModuleService):
    """复验服务：路由层与通用资源层共用同一个实例，保证引用与凭据状态一致。"""

    MODULE = "signoff_reverify"
    ENTITY = "复验凭据"
    OPERATION_TERM = "复验"
    LIST_FIELDS = [
        "复验编号", "关联字幕包", "历史版本", "复验结论", "实际摘要",
        "原签收摘要", "正式引用", "引用状态", "真实引用数", "待办",
    ]
    REQUIRED_FIELDS = ["复验编号", "关联字幕包"]
    STATUS_ORDER = ["待复验", "已通过", "不通过"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS = ["不通过"]

    def __init__(self) -> None:
        self.archive = SignoffArchive()
        for body in ARCHIVED_BODIES:
            self.archive.archive(
                body["version_id"], body["version_no"],
                body["body"], body.get("archived_at", ""),
            )
        self.verifier = SignoffReverifier()
        self.packs: dict[str, SignoffPack] = {
            item["pack_id"].upper(): SignoffPack(**item) for item in HISTORICAL_PACKS
        }
        # 包号、接收人与签收日期以字幕包模块和交付回执模块的既有记录为准。
        self._hydrate_from_store()
        # 引用登记：签收已完成，但正式引用写入中断，等待复验后补全。
        self._references: dict[str, dict[str, Any]] = {
            pack_id: {
                "version_id": pack.version_id,
                "version_no": pack.version_no,
                "state": "引用中断",
                "reference_id": "",
            }
            for pack_id, pack in self.packs.items()
        }
        # 复验凭据不可变追加：每次复验都留一条，刷新或重新查询仍可追溯。
        self._credentials: list[dict[str, Any]] = []
        # 复验前记录版本的引用基线，避免覆盖其他链路已经写入的引用。
        self._baseline_refs = {
            str(row.get("版本编号")): int(row.get("被引用次数", "0") or 0)
            for row in store.rows("transcript_version")
        }
        self._ensure_rows()

    # ---------------------------------------------------------------- 初始化
    def _hydrate_from_store(self) -> None:
        """用字幕包与交付回执模块的既有记录校准包信息。

        包号必须真的存在于字幕包模块；接收人与签收日期取该包最近一次已签收回执。
        对不上号的包不纳入复验范围，避免页面出现「幽灵包」。
        """
        pack_rows = {
            str(row.get("字幕包编号", "")).upper(): row
            for row in store.rows("subtitle_pack")
        }
        receipts: dict[str, dict[str, Any]] = {}
        for row in store.rows("delivery_receipt"):
            if str(row.get("交付结论", "")).strip() == "签收" or row.get("status") == "已签收":
                receipts[str(row.get("关联字幕包", "")).upper()] = row

        for key in list(self.packs):
            pack = self.packs[key]
            pack_row = pack_rows.get(key)
            if pack_row is None:
                self.packs.pop(key)
                continue
            receipt = receipts.get(key)
            if receipt is not None:
                pack.receiver = str(receipt.get("接收方标识") or pack.receiver)
                signed_at = str(receipt.get("交付时间") or "").strip()
                if signed_at and signed_at != "-":
                    pack.signed_at = signed_at
            # 绑定版本以字幕包模块为准；若包记录被改成非 V1，复验会被拒。
            bound_version = str(pack_row.get("绑定版本") or "").strip()
            if bound_version:
                pack.version_no = bound_version

    def _ensure_rows(self) -> None:
        """补齐复验凭据行，保证每个历史签收包都有一条可查询的复验状态。"""
        rows = store.rows(self.MODULE)
        existing = {str(row.get("关联字幕包", "")).upper() for row in rows}
        for pack_id, pack in self.packs.items():
            if pack_id in existing:
                continue
            rows.append({
                "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
                "status": "待复验",
                "pending": True,
                "abnormal": False,
                "复验编号": f"RVFY-{len(rows) + 1:04d}",
                "关联字幕包": pack.pack_id,
                "历史版本": pack.version_no,
                "复验结论": "待复验",
                "实际摘要": "-",
                "原签收摘要": pack.signoff_digest,
                "正式引用": "无",
                "引用状态": UNCONFIRMED_STATE,
                "真实引用数": str(self.real_ref_count(pack.version_id)),
                "待办": f"接收人 {pack.receiver}：补报有效的原签收摘要及字幕",
                "归档摘要": V1_DIGEST,
                "复验说明": "签收当时的 V1 正文已归档，正式引用写入中断",
                "复验时间": "-",
            })

    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """列表返回前先按当前引用状态刷新派生字段，保证刷新后仍与历史引用一致。"""
        self._refresh_rows()
        return super().list_entries(
            filters=filters, keyword=keyword, status=status, page=page, size=size)

    def _refresh_rows(self) -> None:
        for pack_id, pack in self.packs.items():
            row = self.row_for_pack(pack_id)
            if row is None:
                continue
            reference = self._reference_payload(pack)
            row["真实引用数"] = str(reference["real_ref_count"])
            row["引用状态"] = reference["state"]
            if reference["confirmed"]:
                row["正式引用"] = reference["reference_id"]
                row["引用状态"] = CONFIRMED_STATE
                row["待办"] = reference["next_handler"]
            elif str(row.get("正式引用", "无")) not in ("", "无"):
                # 引用登记被外部撤销时，未确认引用不能继续显示为正式引用。
                row["正式引用"] = "无"

    # ---------------------------------------------------------------- 查询
    def find_pack(self, pack_id: str) -> SignoffPack | None:
        return self.packs.get(str(pack_id or "").strip().upper())

    def row_for_pack(self, pack_id: str) -> dict[str, Any] | None:
        key = str(pack_id or "").strip().upper()
        for row in store.rows(self.MODULE):
            if str(row.get("关联字幕包", "")).strip().upper() == key:
                return row
        return None

    def real_ref_count(self, version_id: str) -> int:
        """真实引用数：版本原有引用 + 已确认的正式引用，未确认引用不计数。"""
        baseline = self._baseline_refs.get(version_id, self._current_version_refs(version_id))
        confirmed = sum(
            1 for ref in self._references.values()
            if ref["version_id"] == version_id and ref["state"] == "已确认"
        )
        return baseline + confirmed

    def _current_version_refs(self, version_id: str) -> int:
        for row in store.rows("transcript_version"):
            if row.get("版本编号") == version_id:
                return int(row.get("被引用次数", "0") or 0)
        return 0

    def _sync_version_reference(self, version_id: str) -> int:
        """把真实引用数回写到对应的转写版本记录。"""
        count = self.real_ref_count(version_id)
        for row in store.rows("transcript_version"):
            if row.get("版本编号") == version_id:
                row["被引用次数"] = str(count)
        return count

    def _reference_payload(self, pack: SignoffPack) -> dict[str, Any]:
        ref = self._references[pack.pack_id.upper()]
        row = self.row_for_pack(pack.pack_id) or {}
        confirmed = ref["state"] == "已确认"
        next_handler = "无需办理（正式引用已补全）" if confirmed else str(row.get("待办") or "")
        return {
            "confirmed": confirmed,
            "formal_reference": confirmed,
            "reference_id": ref["reference_id"],
            "state": CONFIRMED_STATE if confirmed else UNCONFIRMED_STATE,
            "version_id": pack.version_id,
            "version_no": pack.version_no,
            "real_ref_count": self.real_ref_count(pack.version_id),
            "next_handler": next_handler,
            "needs_handler": bool(next_handler and not confirmed),
        }

    def packs_payload(self) -> list[dict[str, Any]]:
        """全部历史签收包及其当前复验/引用状态，供复验页按包号选择。"""
        payload: list[dict[str, Any]] = []
        for pack_id, pack in self.packs.items():
            row = self.row_for_pack(pack_id) or {}
            reference = self._reference_payload(pack)
            payload.append({
                "pack_id": pack.pack_id,
                "media_id": pack.media_id,
                "version_id": pack.version_id,
                "version_no": pack.version_no,
                "signoff_digest": pack.signoff_digest,
                "receiver": pack.receiver,
                "signed_at": pack.signed_at,
                "status": row.get("status", "待复验"),
                "verdict": row.get("复验结论", "待复验"),
                "archived_digest": str(row.get("归档摘要", V1_DIGEST)),
                "reference_confirmed": reference["confirmed"],
                "reference_state": reference["state"],
                "reference_id": reference["reference_id"],
                "real_ref_count": reference["real_ref_count"],
                "next_handler": reference["next_handler"],
                "needs_handler": reference["needs_handler"],
            })
        return payload

    def credentials_payload(self) -> list[dict[str, Any]]:
        return list(self._credentials)

    def summary(self) -> dict[str, Any]:
        packs = self.packs_payload()
        return {
            "total": len(packs),
            "confirmed": sum(1 for item in packs if item["reference_confirmed"]),
            "unconfirmed": sum(1 for item in packs if not item["reference_confirmed"]),
            "credentials": len(self._credentials),
        }

    # ---------------------------------------------------------------- 复验
    def verify(
        self,
        pack_id: str,
        signoff_digest: str,
        subtitles: str,
        operator: str = "",
    ) -> tuple[dict[str, Any] | None, str, int]:
        """执行一次复验，返回 (结果, 提示, 建议 HTTP 状态码)。"""
        pack = self.find_pack(pack_id)
        if pack is None:
            return None, f"未找到已签收的字幕包 {pack_id}，请按历史包号复验", 404

        row = self.row_for_pack(pack.pack_id)
        already_confirmed = self._references[pack.pack_id.upper()]["state"] == "已确认"
        outcome = self.verifier.verify(
            pack, self.archive, signoff_digest, subtitles)

        if outcome.ok:
            became_formal = not already_confirmed
            reference = self._confirm_reference(pack)
            self._apply_success(row, pack, outcome, reference, operator)
            result = self._result_payload(
                pack, outcome, reference, row, became_formal)
            return result, outcome.message, 200

        reference = self._reference_payload(pack)
        if already_confirmed:
            # 正式引用一旦补全即永久保留，后续不通过的复验不得撤销既有引用。
            outcome.notes.append("该字幕包已有正式引用，本次不通过不改变既有引用")
            credential = self._save_credential(pack, outcome, reference, operator)
            result = self._result_payload(pack, outcome, reference, row, False)
            result["credential"] = credential
            return result, outcome.message, 200

        self._apply_failure(row, pack, outcome, operator)
        result = self._result_payload(pack, outcome, reference, row, False)
        return result, outcome.message, 200

    def _confirm_reference(self, pack: SignoffPack) -> dict[str, Any]:
        ref = self._references[pack.pack_id.upper()]
        if ref["state"] != "已确认":
            ref["state"] = "已确认"
            ref["reference_id"] = f"REF-{pack.pack_id}"
            ref["version_id"] = pack.version_id
            ref["version_no"] = pack.version_no
        self._sync_version_reference(pack.version_id)
        return self._reference_payload(pack)

    def _apply_success(
        self,
        row: dict[str, Any] | None,
        pack: SignoffPack,
        outcome: ReverifyOutcome,
        reference: dict[str, Any],
        operator: str,
    ) -> None:
        credential = self._save_credential(pack, outcome, reference, operator)
        if row is not None:
            row.update({
                "status": "已通过",
                "pending": False,
                "abnormal": False,
                "复验结论": "通过",
                "实际摘要": outcome.computed_digest,
                # 原签收摘要始终保留签收当时的历史值，不被提交内容覆盖。
                "原签收摘要": pack.signoff_digest,
                "正式引用": reference["reference_id"],
                "引用状态": CONFIRMED_STATE,
                "真实引用数": str(reference["real_ref_count"]),
                "待办": "无需办理（正式引用已补全）",
                "归档摘要": outcome.archived_digest,
                "复验说明": outcome.message,
                "复验时间": _now(),
                "凭据编号": credential["credential_id"],
            })

    def _apply_failure(
        self,
        row: dict[str, Any] | None,
        pack: SignoffPack,
        outcome: ReverifyOutcome,
        operator: str,
    ) -> None:
        reference = self._reference_payload(pack)
        credential = self._save_credential(pack, outcome, reference, operator)
        if row is not None:
            row.update({
                "status": "不通过",
                "pending": False,
                "abnormal": True,
                "复验结论": "不通过",
                "实际摘要": outcome.computed_digest or "-",
                # 历史原签收摘要只读，不因一次不通过的提交而改变。
                "原签收摘要": pack.signoff_digest,
                "正式引用": "无",
                "引用状态": UNCONFIRMED_STATE,
                "真实引用数": str(reference["real_ref_count"]),
                "待办": outcome.next_handler
                or f"接收人 {pack.receiver}：补报有效的原签收摘要及字幕",
                "归档摘要": outcome.archived_digest or V1_DIGEST,
                "复验说明": outcome.message,
                "复验时间": _now(),
                "凭据编号": credential["credential_id"],
            })

    def _save_credential(
        self,
        pack: SignoffPack,
        outcome: ReverifyOutcome,
        reference: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        """永久追加一条归档凭据。"""
        credential = {
            "credential_id": f"CRED-{pack.pack_id}-{len(self._credentials) + 1:03d}",
            "pack_id": pack.pack_id,
            "media_id": pack.media_id,
            "version_id": pack.version_id,
            "version_no": pack.version_no,
            "receiver": pack.receiver,
            "signed_at": pack.signed_at,
            "submitted_digest": outcome.submitted_digest,
            "computed_digest": outcome.computed_digest,
            "archived_digest": outcome.archived_digest or V1_DIGEST,
            "verdict": outcome.verdict,
            "code": outcome.code,
            "notes": list(outcome.notes),
            "message": outcome.message,
            "reference_id": reference["reference_id"],
            "reference_confirmed": reference["confirmed"],
            "real_ref_count": reference["real_ref_count"],
            "operator": operator or pack.receiver,
            "created_at": _now(),
        }
        self._credentials.append(credential)
        return credential

    def _result_payload(
        self,
        pack: SignoffPack,
        outcome: ReverifyOutcome,
        reference: dict[str, Any],
        row: dict[str, Any] | None,
        became_formal: bool,
    ) -> dict[str, Any]:
        return {
            "ok": outcome.ok,
            "message": outcome.message,
            "verdict": outcome.verdict,
            "code": outcome.code,
            "notes": list(outcome.notes),
            "pack_id": pack.pack_id,
            "entry": row,
            "credential": self._credentials[-1] if self._credentials else None,
            "reference": reference,
            # 便于页面与外部调用方直接读取的关键结论。
            "formal_reference": reference["confirmed"],
            "became_formal_reference": bool(became_formal and reference["confirmed"]),
            "reference_state": reference["state"],
            "reference_id": reference["reference_id"],
            "real_ref_count": reference["real_ref_count"],
            "next_handler": reference["next_handler"],
            "needs_handler": reference["needs_handler"],
            "checks": {
                "submitted_digest": outcome.submitted_digest,
                "computed_digest": outcome.computed_digest,
                "archived_digest": outcome.archived_digest,
            },
        }


# 单例：路由层和通用资源注册表必须共享同一份引用与凭据状态。
signoff_reverify_service = SignoffReverifyService()
