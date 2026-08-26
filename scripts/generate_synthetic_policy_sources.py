"""Materialize the reviewed synthetic Markdown source fixtures once.

This is not called by the corpus build. The build treats files under raw/ as
immutable source inputs and writes only normalized/, clauses/, manifests/, and reports/.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "policy_corpus" / "raw"

POLICIES = (
    "RETURN_EXCHANGE",
    "SHIPPING_DAMAGE",
    "LEAKAGE_CONTAMINATION",
    "MISSING_COMPONENT",
    "EVIDENCE_REQUIREMENT",
    "HIGH_RISK_EXCEPTION",
    "WRONG_ITEM",
    "FUNCTIONAL_FAILURE",
    "PACKAGING_DAMAGE",
)


def _specs() -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for tenant, prefix, days in (
        ("csight-demo-retail", "RTL", "7"),
        ("csight-demo-brand", "BRD", "14"),
    ):
        for index, policy_type in enumerate(POLICIES, start=1):
            logical = f"POLICY-{prefix}-{index:03d}"
            if index <= 3:
                specs.append(
                    {
                        "tenant": tenant,
                        "document_id": logical,
                        "version": "1.0.0",
                        "policy_type": policy_type,
                        "status": "RETIRED",
                        "effective_from": "2025-01-01",
                        "effective_to": "2025-12-31",
                        "supersedes": "",
                        "superseded_by": f"{logical}@2.0.0",
                        "days": days,
                    }
                )
                version = "2.0.0"
                supersedes = f"{logical}@1.0.0"
            else:
                version = "1.0.0"
                supersedes = ""
            specs.append(
                {
                    "tenant": tenant,
                    "document_id": logical,
                    "version": version,
                    "policy_type": policy_type,
                    "status": "ACTIVE",
                    "effective_from": "2026-01-01" if index != 9 else "2027-01-01",
                    "effective_to": "",
                    "supersedes": supersedes,
                    "superseded_by": "",
                    "days": days,
                }
            )
    return specs


def _render(spec: dict[str, str]) -> str:
    tenant = spec["tenant"]
    policy = spec["policy_type"]
    identity = f"{spec['document_id']} {spec['version']} {tenant}"
    defect = {
        "RETURN_EXCHANGE": "BREAKAGE",
        "SHIPPING_DAMAGE": "PACKAGING_DAMAGE",
        "LEAKAGE_CONTAMINATION": "LEAKAGE",
        "MISSING_COMPONENT": "MISSING_COMPONENT",
        "EVIDENCE_REQUIREMENT": "CONTAMINATION",
        "HIGH_RISK_EXCEPTION": "CONTAMINATION",
        "WRONG_ITEM": "WRONG_ITEM",
        "FUNCTIONAL_FAILURE": "FUNCTIONAL_FAILURE",
        "PACKAGING_DAMAGE": "PACKAGING_DAMAGE",
    }[policy]
    title = f"{policy.replace('_', ' ').title()} 합성 참조 정책"
    clauses = (
        (
            "C1",
            "RULE",
            f"{identity}의 {defect} 접수는 수령 후 {spec['days']}일 이내이면 "
            "검토 대상으로 분류한다.",
            "",
        ),
        (
            "C2",
            "EVIDENCE_REQUIREMENT",
            f"{identity}의 {defect} 검토에는 상품 전체와 결함 부위가 보이는 이미지가 필요하다.",
            "",
        ),
        (
            "C3",
            "EXCEPTION",
            f"{identity}에서 안전 위해 또는 오염 확산 우려가 있으면 일반 기간 조건보다 "
            "격리 검토를 우선한다.",
            "C1",
        ),
        (
            "C4",
            "RULE",
            f"{identity}의 요청 유형은 고객이 명시한 요청과 확인된 증거를 분리해 기록한다.",
            "",
        ),
        (
            "C5",
            "EVIDENCE_REQUIREMENT",
            f"{identity}의 증거에는 주문 참조와 상품 참조를 함께 확인해야 한다.",
            "",
        ),
        (
            "C6",
            "EXCEPTION",
            f"{identity}에서 이미지 품질이 판독 불가이면 결론을 내리지 않고 추가 증거를 요청한다.",
            "C4",
        ),
        (
            "C7",
            "ESCALATION",
            f"{identity}의 고위험 조건이나 상충 증거는 사람 검토로 이관하며 자동 승인하지 않는다.",
            "",
        ),
    )
    header = f"""---
tenant_id: {tenant}
document_id: {spec["document_id"]}
document_version: {spec["version"]}
title: {title}
policy_type: {policy}
authority_level: CORPORATE_POLICY
product_categories: GENERAL
effective_from: {spec["effective_from"]}
effective_to:{f" {spec['effective_to']}" if spec["effective_to"] else ""}
status: {spec["status"]}
source_type: SYNTHETIC_REFERENCE
supersedes:{f" {spec['supersedes']}" if spec["supersedes"] else ""}
superseded_by:{f" {spec['superseded_by']}" if spec["superseded_by"] else ""}
---
# {title}

> 이 문서는 CSight PoC 검색·평가용 합성 Reference이며 실제 기업 정책이나 법률 자문이 아니다.
"""
    sections = []
    for number, clause_type, text, parent in clauses:
        parent_tag = f"; parent={parent}" if parent else ""
        sections.append(
            f"## {number} [{clause_type}]\n\n{text}\n\n"
            f"Tags: defects={defect}; actions=REVIEW; categories=GENERAL{parent_tag}\n"
        )
    return header + "\n".join(sections)


def main() -> None:
    for spec in _specs():
        tenant_dir = RAW / spec["tenant"]
        tenant_dir.mkdir(parents=True, exist_ok=True)
        path = tenant_dir / f"{spec['document_id'].lower()}-{spec['version']}.md"
        path.write_text(_render(spec), encoding="utf-8")


if __name__ == "__main__":
    main()
