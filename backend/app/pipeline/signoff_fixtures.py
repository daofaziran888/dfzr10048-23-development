"""签收复验示例数据：历史签收包与签收当时的版本文本。

这些文本模拟「签收当时已经落库的 V1 正文」以及后来出现的 V2/V3 文本，
复验只允许使用 V1 正文，V2/V3 仅用于判定不通过。
"""
from __future__ import annotations

from typing import Any

from app.digest import text_digest

# 签收当时归档的 V1 正文（历史旧包 SBPK-0004/SBPK-0005 都指向这份正文）。
V1_BODY = "\n".join([
    "各位来宾大家好，今天我们共同探讨AI技术在内容生产中的应用。",
    "在过去的一年里，我们的模型在多项基准测试中取得了领先成绩。",
    "下面由产品总监为大家详细介绍新一代采集架构的设计理念。",
])

# 后来纠错产生的 V2 正文：只能用于识别「拿 V2 来复验」，不能参与通过判定。
V2_BODY = "\n".join([
    "各位来宾大家好，今天我们共同探讨人工智能技术在内容生产中的应用。",
    "在过去一年中，我们的模型于多项基准测试中取得领先成绩。",
    "下面由产品总监详细介绍新一代数据采集流水线架构。",
])

V3_BODY = "\n".join([
    "各位来宾大家好，今天我们共同探讨人工智能技术在内容生产中的应用。",
    "在过去一年中，我们的模型于多项基准测试中取得了领先成绩。",
    "接下来由产品总监详细介绍新一代数据采集流水线架构与实施路径。",
])

# 与 V1 正文文字完全相同、但签收摘要对不上的另一旧包记录的原摘要。
LURE_SIGNOFF_DIGEST = text_digest("SBPK-0005 旧包签收摘要（与正文不符）")

V1_DIGEST = text_digest(V1_BODY)


# 历史签收包：签收已完成，但正式引用写入中断，等待复验补全。
HISTORICAL_PACKS: list[dict[str, Any]] = [
    {
        "pack_id": "SBPK-0004",
        "media_id": "MEDI-0001",
        "version_id": "TRSV-0001",
        "version_no": "v1",
        "signoff_digest": V1_DIGEST,
        "receiver": "内容分发平台A",
        "signed_at": "2026-09-02",
    },
    {
        "pack_id": "SBPK-0005",
        "media_id": "MEDI-0002",
        "version_id": "TRSV-0001",
        "version_no": "v1",
        "signoff_digest": LURE_SIGNOFF_DIGEST,
        "receiver": "视频归档系统",
        "signed_at": "2026-09-01",
    },
]


ARCHIVED_BODIES: list[dict[str, str]] = [
    {"version_id": "TRSV-0001", "version_no": "v1", "body": V1_BODY, "archived_at": "2026-09-02"},
    {"version_id": "TRSV-0002", "version_no": "v2", "body": V2_BODY, "archived_at": "2026-09-05"},
    {"version_id": "TRSV-0003", "version_no": "v3", "body": V3_BODY, "archived_at": "2026-09-08"},
]


def seed_reverify_rows() -> list[dict[str, Any]]:
    """复验凭据表的初始行：每个历史签收包一条，引用均未确认。"""
    rows: list[dict[str, Any]] = []
    for index, pack in enumerate(HISTORICAL_PACKS, start=1):
        rows.append({
            "id": index,
            "status": "待复验",
            "pending": True,
            "abnormal": False,
            "复验编号": f"RVFY-{index:04d}",
            "关联字幕包": pack["pack_id"],
            "历史版本": pack["version_no"],
            "复验结论": "待复验",
            "实际摘要": "-",
            "原签收摘要": pack["signoff_digest"],
            "正式引用": "无",
            "引用状态": "引用中断（未确认）",
            "真实引用数": "0",
            "待办": f"接收人 {pack['receiver']}：补报有效的原签收摘要及字幕",
            "归档摘要": V1_DIGEST,
            "复验说明": "签收当时的 V1 正文已归档，正式引用写入中断",
            "复验时间": "-",
        })
    return rows
