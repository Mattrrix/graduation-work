import json
import logging
from uuid import UUID

import asyncpg

from . import clients
from .config import settings
from .stages import classify, dedup, ner, normalize, reconcile, validate

logger = logging.getLogger(__name__)


def _flat_from_llm(llm_output: dict) -> dict:
    fields: dict = {}

    primary_cp = next(
        (cp for cp in llm_output.get("counterparties") or [] if isinstance(cp, dict) and cp.get("is_primary")),
        None,
    )
    if primary_cp:
        if primary_cp.get("name"):
            fields["counterparty_name"] = primary_cp["name"]
        if primary_cp.get("inn"):
            fields["inn"] = primary_cp["inn"]
        if primary_cp.get("kpp"):
            fields["kpp"] = primary_cp["kpp"]

    dates = [d for d in (llm_output.get("dates") or []) if isinstance(d, dict) and d.get("value")]
    primary_date = next((d["value"] for d in dates if d.get("role") == "doc_date"), None)
    if not primary_date and dates:
        primary_date = dates[0]["value"]
    if primary_date:
        fields["date"] = primary_date
        fields["dates_all"] = [d["value"] for d in dates]

    amounts = [
        a for a in (llm_output.get("amounts") or [])
        if isinstance(a, dict) and a.get("value") and a.get("role") in ("total", "vat")
    ]
    primary_amount = next((a["value"] for a in amounts if a.get("role") == "total"), None)
    if not primary_amount and amounts:
        primary_amount = amounts[0]["value"]
    if primary_amount:
        fields["amount_total"] = primary_amount

    if llm_output.get("doc_number"):
        fields["number"] = llm_output["doc_number"]

    return fields


DOC_TYPE_LABELS_RU = {
    "invoice": "Счёт-фактура",
    "act": "Акт",
    "contract": "Договор",
    "waybill": "ТОРГ-12 (накладная)",
    "upd": "УПД",
    "payment_order": "Платёжное поручение",
}


ISSUE_LABELS_RU = {
    "unknown_document_type": "не удалось определить тип документа",
    "llm_unavailable": "LLM была недоступна",
    "llm_disabled": "LLM выключена в конфигурации",
    "checksum_failed": "ИНН не прошёл проверку контрольной суммы",
    "format_invalid": "некорректный формат значения",
    "out_of_range_or_format": "дата вне допустимого диапазона",
    "non_positive_or_format": "сумма должна быть положительной",
    "hallucinated": "значение отсутствует в тексте",
}


FIELD_LABELS_RU = {
    "document": "тип документа",
    "inn": "ИНН",
    "kpp": "КПП",
    "date": "дата",
    "amount": "сумма",
    "amount_total": "сумма",
    "number": "номер",
    "doc_number": "номер",
    "counterparty_name": "контрагент",
    "vat_rate": "ставка НДС",
}


def _summarize_issues(issues: list[dict], limit: int = 3) -> str:
    if not issues:
        return ""
    parts: list[str] = []
    for it in issues[:limit]:
        code = it.get("code", "")
        field = it.get("field", "")
        label = ISSUE_LABELS_RU.get(code) or code
        if field and field != "_pipeline" and field != "document":
            parts.append(f"{FIELD_LABELS_RU.get(field, field)}: {label}")
        else:
            parts.append(label)
    suffix = f", и ещё {len(issues) - limit}" if len(issues) > limit else ""
    return "; ".join(parts) + suffix


def _ru_plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n)
    n100 = n % 100
    if 11 <= n100 <= 14:
        return forms[2]
    n10 = n % 10
    if n10 == 1:
        return forms[0]
    if 2 <= n10 <= 4:
        return forms[1]
    return forms[2]


async def _emit(conn, doc_id, stage: str, status: str, message: str, payload: dict | None = None) -> None:
    await conn.execute(
        """
        INSERT INTO processing_events(doc_id, stage, status, message, payload, created_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, clock_timestamp())
        """,
        doc_id,
        stage,
        status,
        message,
        json.dumps(payload, ensure_ascii=False) if payload else None,
    )


async def _set_status(conn, doc_id, status: str) -> None:
    await conn.execute(
        "UPDATE documents SET status = $2::doc_status, updated_at = NOW() WHERE doc_id = $1",
        doc_id,
        status,
    )


async def process(conn: asyncpg.Connection, message: dict) -> dict:
    doc_id = UUID(message["doc_id"])
    text = message.get("text") or ""
    filename = message.get("filename")
    sha256 = message.get("sha256") or ""

    exists = await conn.fetchval("SELECT 1 FROM documents WHERE doc_id = $1", doc_id)
    if not exists:
        logger.info("doc_id=%s deleted before transform — skipping", doc_id)
        return {"doc_type": "unknown", "status": "skipped_deleted"}

    candidates = ner.find_candidates(text)
    doc_type: str | None = None

    n_inn = len(candidates["inns"])
    n_num = len(candidates["numbers"])
    n_amt = len(candidates["amounts"])
    await _emit(
        conn, doc_id, "candidates", "ok",
        f"Найдено кандидатов: {n_inn} {_ru_plural(n_inn, ('ИНН', 'ИНН', 'ИНН'))}, "
        f"{n_num} {_ru_plural(n_num, ('номер', 'номера', 'номеров'))}, "
        f"{n_amt} {_ru_plural(n_amt, ('сумма', 'суммы', 'сумм'))}",
        {"candidates_count": {k: len(v) for k, v in candidates.items()}},
    )

    has_business_candidates = any(candidates[k] for k in ("inns", "numbers", "amounts"))

    llm_output: dict | None = None
    llm_status = "ok"
    pipeline_warnings: list[dict] = []

    if not doc_type and not has_business_candidates:
        llm_status = "skipped_no_candidates"
        await _emit(conn, doc_id, "llm", "skipped", "Пропущено — нечего извлекать")
    elif not settings.llm_enabled:
        llm_status = "disabled"
        pipeline_warnings.append({
            "field": "_pipeline",
            "code": "llm_disabled",
            "value": "LLM disabled by config",
            "severity": "warning",
        })
        await _emit(conn, doc_id, "llm", "warning", "LLM выключена в конфигурации")
    else:
        try:
            llm_output = await clients.extract(text, filename=filename)
            n_cp = len(llm_output.get("counterparties") or [])
            n_d = len(llm_output.get("dates") or [])
            n_a = len(llm_output.get("amounts") or [])
            msg = (
                f"Извлечено: {n_cp} {_ru_plural(n_cp, ('контрагент', 'контрагента', 'контрагентов'))}, "
                f"{n_d} {_ru_plural(n_d, ('дата', 'даты', 'дат'))}, "
                f"{n_a} {_ru_plural(n_a, ('сумма', 'суммы', 'сумм'))}"
            )
            await _emit(conn, doc_id, "llm", "ok", msg)
        except clients.LLMError as e:
            llm_status = f"failed: {str(e)[:60]}"
            logger.warning("llm failed for doc_id=%s backend=%s: %s", doc_id, settings.llm_backend, e)
            pipeline_warnings.append({
                "field": "_pipeline",
                "code": "llm_unavailable",
                "value": str(e)[:120],
                "severity": "warning",
            })
            await _emit(conn, doc_id, "llm", "error", "LLM была недоступна")

    if llm_output is not None:
        llm_output, recon_warnings = reconcile.reconcile(text, candidates, llm_output)
        pipeline_warnings.extend(recon_warnings)
        llm_dt = llm_output.get("doc_type")
        try:
            llm_conf = float(llm_output.get("doc_type_confidence") or 0)
        except (TypeError, ValueError):
            llm_conf = 0.0
        valid_types = {"invoice", "act", "contract", "waybill", "upd", "payment_order"}

        if llm_dt in valid_types and llm_conf >= 0.7:
            doc_type = llm_dt
            await _emit(
                conn, doc_id, "classify", "ok",
                f"LLM определил тип: {DOC_TYPE_LABELS_RU.get(llm_dt, llm_dt)} (уверенность {int(llm_conf * 100)}%)",
                {"doc_type": llm_dt, "confidence": llm_conf, "backend": settings.llm_backend},
            )
        else:
            llm_label = DOC_TYPE_LABELS_RU.get(llm_dt, llm_dt) if llm_dt else "не определён"
            await _emit(
                conn, doc_id, "classify", "warning",
                f"LLM не уверен в типе документа (предположение: {llm_label}, {int(llm_conf * 100)}%)",
                {"llm_doc_type": llm_dt, "confidence": llm_conf, "backend": settings.llm_backend},
            )

        recon_summary = _summarize_issues(recon_warnings)
        recon_msg = f"Найдено замечаний: {len(recon_warnings)}" + (f" ({recon_summary})" if recon_summary else "")
        await _emit(
            conn, doc_id, "reconcile", "ok" if not recon_warnings else "warning",
            recon_msg,
        )

    flat = _flat_from_llm(llm_output) if llm_output else {}
    normalized = normalize.normalize(flat)
    errors = validate.validate(normalized)

    llm_tech_failure = llm_status.startswith("failed") or llm_status == "disabled"
    if not llm_tech_failure:
        has_business_field = any(k in normalized for k in ("inn", "number", "amount_total"))
        if not doc_type or not has_business_field:
            doc_type = None
            errors.append({"field": "document", "code": "unknown_document_type", "value": None})

    all_issues = errors + pipeline_warnings
    has_real_issue = any(i.get("severity") != "info" for i in all_issues)
    status = "validated_with_errors" if has_real_issue else "loaded"

    issues_summary = _summarize_issues(all_issues)
    validate_msg = f"Найдено замечаний: {len(all_issues)}" + (f" ({issues_summary})" if issues_summary else "")
    await _emit(
        conn, doc_id, "validate", "ok" if not has_real_issue else "warning",
        validate_msg,
        {"errors": all_issues} if all_issues else None,
    )

    duplicate_of = await dedup.find_exact_duplicate(conn, sha256, doc_id) if sha256 else None

    raw_amounts = (llm_output or {}).get("amounts") or []
    filtered_amounts = [
        a for a in raw_amounts
        if isinstance(a, dict) and a.get("value") and a.get("role") in ("total", "vat")
    ]
    fields_payload = {
        **normalized,
        "candidates": candidates,
        "counterparties": (llm_output or {}).get("counterparties") or [],
        "dates": (llm_output or {}).get("dates") or [],
        "amounts": filtered_amounts,
        "summary": (llm_output or {}).get("summary"),
        "errors": all_issues,
        "duplicate_of": duplicate_of,
        "llm_status": llm_status,
    }

    vat_rate_raw = (llm_output or {}).get("vat_rate")
    vat_rate_str = str(vat_rate_raw).replace(",", ".") if vat_rate_raw not in (None, "") else ""

    await conn.execute(
        """
        UPDATE documents
           SET status            = $2::doc_status,
               doc_type          = $3,
               number            = $4,
               doc_date          = NULLIF($5, '')::date,
               counterparty_name = $6,
               counterparty_inn  = $7,
               counterparty_kpp  = $8,
               amount_total      = NULLIF($9, '')::numeric,
               fields            = $10::jsonb,
               summary           = $11,
               vat_rate          = NULLIF($12, '')::numeric,
               updated_at        = NOW()
         WHERE doc_id = $1
        """,
        doc_id,
        status,
        doc_type,
        normalized.get("number"),
        normalized.get("date") or "",
        normalized.get("counterparty_name"),
        normalized.get("inn"),
        normalized.get("kpp"),
        normalized.get("amount_total") or "",
        json.dumps(fields_payload, ensure_ascii=False, default=str),
        (llm_output or {}).get("summary"),
        vat_rate_str,
    )

    await _emit(
        conn, doc_id, "load", "ok" if not has_real_issue else "warning",
        "Документ сохранён в БД",
        {"errors": all_issues, "duplicate_of": duplicate_of, "llm_status": llm_status, "doc_type": doc_type, "status": status},
    )

    logger.info(
        "processed doc_id=%s type=%s issues=%d llm=%s dup=%s",
        doc_id, doc_type, len(all_issues), llm_status, duplicate_of,
    )
    return {"doc_type": doc_type or "unknown", "status": status}
