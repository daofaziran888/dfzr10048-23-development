"""签收正文复验测试：历史包号、V1 正文、原摘要与正式引用的边界。"""
from __future__ import annotations

from app.digest import canonical_text, digest_equivalent, normalize_digest, text_digest
from app.pipeline.signoff_fixtures import (
    LURE_SIGNOFF_DIGEST,
    V1_BODY,
    V1_DIGEST,
    V2_BODY,
)
from app.pipeline.signoff_reverifier import (
    SignoffArchive,
    SignoffPack,
    SignoffReverifier,
)
from app.services.signoff_reverify import SignoffReverifyService, signoff_reverify_service
from app.store import store


def _service() -> SignoffReverifyService:
    """每个用例一份独立服务，避免用例之间共享引用状态。"""
    return SignoffReverifyService()


def _pack(pack_id: str) -> SignoffPack:
    return next(p for p in _service().packs.values() if p.pack_id == pack_id)


class TestDigestCanonicalization:
    def test_newlines_and_blank_lines_normalised(self):
        left = "第一行\r\n\r\n第二行\r\n"
        right = "第一行\n第二行"
        assert canonical_text(left) == canonical_text(right)
        assert text_digest(left) == text_digest(right)

    def test_leading_trailing_spaces_ignored(self):
        assert text_digest("  第一行  \n 第二行 ") == text_digest("第一行\n第二行")

    def test_content_change_changes_digest(self):
        assert text_digest(V1_BODY) != text_digest(V2_BODY)

    def test_digest_prefix_compatibility(self):
        assert digest_equivalent(V1_DIGEST[:8], V1_DIGEST)
        assert not digest_equivalent(V1_DIGEST[:8], V2_BODY)

    def test_normalize_digest(self):
        assert normalize_digest(" MD5:AA-BB-CC ") == "aabbcc"


class TestSignoffArchive:
    def test_body_is_immutable(self):
        archive = SignoffArchive()
        archive.archive("TRSV-0001", "v1", V1_BODY)
        archive.archive("TRSV-0001", "v1", "被篡改的正文")
        archived = archive.get_by_version_no("v1")
        assert archived is not None
        assert archived.body == V1_BODY
        assert archived.digest == V1_DIGEST

    def test_version_lookup_ignores_prefix_case(self):
        archive = SignoffArchive()
        archive.archive("TRSV-0001", "v1", V1_BODY)
        assert archive.get_by_version_no("V1") is not None
        assert archive.get_by_version_no("1") is not None


class TestReverifier:
    def setup_method(self) -> None:
        self.service = _service()
        self.archive = self.service.archive
        self.verifier = SignoffReverifier()

    def test_v1_body_and_digest_pass(self):
        pack = _pack("SBPK-0004")
        outcome = self.verifier.verify(pack, self.archive, pack.signoff_digest, V1_BODY)
        assert outcome.ok
        assert outcome.code == "VERIFIED"

    def test_v2_body_rejected(self):
        pack = _pack("SBPK-0004")
        outcome = self.verifier.verify(pack, self.archive, pack.signoff_digest, V2_BODY)
        assert not outcome.ok
        assert outcome.code == "VERSION_V2_REJECTED"

    def test_wrong_submitted_digest_rejected(self):
        pack = _pack("SBPK-0004")
        outcome = self.verifier.verify(pack, self.archive, "0" * 32, V1_BODY)
        assert not outcome.ok
        assert outcome.code == "DIGEST_MISMATCH"

    def test_missing_subtitles_rejected(self):
        pack = _pack("SBPK-0004")
        outcome = self.verifier.verify(pack, self.archive, pack.signoff_digest, "")
        assert not outcome.ok
        assert outcome.code == "SUBTITLES_MISSING"

    def test_non_v1_pack_never_verified(self):
        pack = SignoffPack(
            pack_id="SBPK-V2", media_id="MEDI-0001", version_id="TRSV-0002",
            version_no="v2", signoff_digest=V1_DIGEST,
            receiver="测试", signed_at="2026-09-05",
        )
        outcome = self.verifier.verify(pack, self.archive, V1_DIGEST, V1_BODY)
        assert not outcome.ok
        assert outcome.code == "VERSION_NOT_V1"


class TestReverifyService:
    def test_success_creates_formal_reference_and_credential(self):
        service = _service()
        pack = service.packs["SBPK-0004"]
        before = service.real_ref_count(pack.version_id)
        result, _, code = service.verify(
            "SBPK-0004", pack.signoff_digest, V1_BODY, "接收人A")
        assert code == 200
        assert result is not None
        assert result["became_formal_reference"] is True
        assert result["formal_reference"] is True
        assert result["reference_state"] == "已确认（正式引用）"
        assert result["real_ref_count"] == before + 1
        assert len(service.credentials_payload()) == 1
        credential = service.credentials_payload()[0]
        assert credential["pack_id"] == "SBPK-0004"
        assert credential["verdict"] == "通过"
        assert credential["computed_digest"] == V1_DIGEST

    def test_success_syncs_transcript_version_ref_count(self):
        service = _service()
        pack = service.packs["SBPK-0004"]
        service.verify("SBPK-0004", pack.signoff_digest, V1_BODY, "接收人A")
        row = next(r for r in store.rows("transcript_version")
                   if r["版本编号"] == pack.version_id)
        assert row["被引用次数"] == str(service.real_ref_count(pack.version_id))

    def test_lure_pack_never_gets_formal_reference(self):
        service = _service()
        pack = service.packs["SBPK-0005"]
        before = service.real_ref_count(pack.version_id)
        # 文字与 V1 相同，但原签收摘要不符。
        result, _, _ = service.verify(
            "SBPK-0005", pack.signoff_digest, V1_BODY, "接收人B")
        assert result is not None
        assert result["ok"] is False
        assert result["code"] == "SIGNOFF_DIGEST_INCONSISTENT"
        assert result["formal_reference"] is False
        assert result["reference_state"] == "引用中断（未确认）"
        assert result["real_ref_count"] == before
        # 换成 V1 的真实摘要也不行，旧包的原摘要就是不符。
        result2, _, _ = service.verify(
            "SBPK-0005", V1_DIGEST, V1_BODY, "接收人B")
        assert result2 is not None
        assert result2["formal_reference"] is False

    def test_unconfirmed_reference_not_shown_as_complete(self):
        service = _service()
        rows, _ = service.list_entries()
        for row in rows:
            assert row["引用状态"] == "引用中断（未确认）"
            assert row["正式引用"] == "无"

    def test_v2_submission_does_not_create_reference(self):
        service = _service()
        pack = service.packs["SBPK-0004"]
        result, _, _ = service.verify(
            "SBPK-0004", pack.signoff_digest, V2_BODY, "接收人A")
        assert result is not None
        assert result["formal_reference"] is False
        assert result["code"] == "VERSION_V2_REJECTED"

    def test_repeated_failure_keeps_credentials(self):
        service = _service()
        pack = service.packs["SBPK-0005"]
        for _ in range(3):
            service.verify("SBPK-0005", pack.signoff_digest, V1_BODY, "接收人B")
        assert len(service.credentials_payload()) == 3
        assert all(item["verdict"] == "不通过"
                   for item in service.credentials_payload())

    def test_confirmed_reference_survives_later_failure(self):
        service = _service()
        pack = service.packs["SBPK-0004"]
        service.verify("SBPK-0004", pack.signoff_digest, V1_BODY, "接收人A")
        result, _, _ = service.verify("SBPK-0004", "0" * 32, V1_BODY, "接收人A")
        assert result is not None
        assert result["formal_reference"] is True
        assert result["notes"], "已经补全的正式引用不应被后续失败撤销"

    def test_list_refresh_tracks_reference_state(self):
        service = _service()
        pack = service.packs["SBPK-0004"]
        service.verify("SBPK-0004", pack.signoff_digest, V1_BODY, "接收人A")
        rows, _ = service.list_entries()
        confirmed = next(r for r in rows if r["关联字幕包"] == "SBPK-0004")
        assert confirmed["引用状态"] == "已确认（正式引用）"
        assert confirmed["正式引用"] == "REF-SBPK-0004"
        assert confirmed["真实引用数"] == str(service.real_ref_count(pack.version_id))

    def test_unknown_pack_reports_not_found(self):
        service = _service()
        result, message, code = service.verify("SBPK-9999", "x", V1_BODY, "")
        assert result is None
        assert code == 404
        assert "SBPK-9999" in message

    def test_payload_exposes_needs_handler_and_real_count(self):
        service = _service()
        pack = service.packs["SBPK-0005"]
        result, _, _ = service.verify(
            "SBPK-0005", pack.signoff_digest, V1_BODY, "接收人B")
        assert result is not None
        assert result["needs_handler"] is True
        assert "接收人" in result["next_handler"]
        assert isinstance(result["real_ref_count"], int)

    def test_shared_singleton_registered(self):
        from app.services import SERVICES
        assert SERVICES["signoff_reverify"] is signoff_reverify_service


class TestSeedRows:
    def test_reverify_rows_seeded(self):
        rows = store.rows("signoff_reverify")
        assert {row["关联字幕包"] for row in rows} >= {"SBPK-0004", "SBPK-0005"}

    def test_lure_seed_digest_mismatch(self):
        assert LURE_SIGNOFF_DIGEST != V1_DIGEST
        assert text_digest(V1_BODY) == V1_DIGEST
