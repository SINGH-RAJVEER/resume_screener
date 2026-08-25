import json
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe
from typing import cast

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing.allowance import next_reset, week_start
from ..billing.quotes import EMPLOYER_QUOTE, INDEPENDENT_QUOTE, UnknownQuoteKindError, point_quote
from ..billing.razorpay import (
    RazorpayClient,
    RazorpayError,
    RazorpayUnavailableError,
    payment_entity,
    verify_checkout_signature,
    verify_webhook_signature,
)
from ..core.http import APIError
from ..persistence.models import (
    OrganizationEntitlement,
    OrganizationMember,
    PointLedgerEntry,
    RazorpayOrder,
    RazorpayPayment,
    RazorpayWebhookEvent,
    WeeklyFreeUse,
)
from ..persistence.points import (
    available_balance,
    balance,
    ensure_organization_account,
    ensure_user_account,
    grant_in_session,
)
from .contracts import ERROR_RESPONSES
from .routes import RequestModel, require_membership, require_sqlalchemy_store, require_user

router = APIRouter(responses=ERROR_RESPONSES)


class OrderRequest(RequestModel):
    pack_id: str
    organization_id: str | None = None


class VerifyCheckoutRequest(RequestModel):
    razorpay_payment_id: str
    razorpay_signature: str


class EntitlementRequest(RequestModel):
    note: str = ""


@router.get("/api/billing/packs")
async def list_packs(request: Request) -> list[dict[str, object]]:
    await require_user(request)
    billing = request.app.state.settings.billing
    return [
        {"id": pack.id, "points": pack.points, "amountInr": pack.amount_inr}
        for pack in billing.packs
    ]


@router.get("/api/billing/quote")
async def get_quote(request: Request, kind: str = Query()) -> dict[str, object]:
    await require_user(request)
    billing = request.app.state.settings.billing
    try:
        quote = point_quote(kind, billing)
    except UnknownQuoteKindError as error:
        raise APIError(400, "INVALID_REQUEST", "Unknown quote kind") from error
    return {
        "kind": quote.kind,
        "points": quote.points,
        "minimumPoints": quote.minimum_points,
        "costCeilingPoints": quote.cost_ceiling_points,
        "lineItems": [
            {
                "task": item.task,
                "maxInputTokens": item.max_input_tokens,
                "maxOutputTokens": item.max_output_tokens,
            }
            for item in quote.line_items
        ],
    }


@router.get("/api/me/points")
async def my_points(
    request: Request, organization_id: str | None = Query(default=None)
) -> dict[str, object]:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions()() as session:
        if organization_id is None:
            account = await ensure_user_account(session, user.id)
            free_used = bool(
                (
                    await session.execute(
                        select(WeeklyFreeUse.id).where(
                            (WeeklyFreeUse.user_id == user.id)
                            & (WeeklyFreeUse.week_start == week_start(datetime.now(UTC)))
                        )
                    )
                ).scalar_one_or_none()
            )
            return {
                "scope": "personal",
                "accountId": account.id,
                "balance": await balance(session, account.id),
                "available": await available_balance(session, account.id),
                "allowance": {
                    "freeUsedThisWeek": free_used,
                    "resetsAt": next_reset(datetime.now(UTC)).isoformat(),
                },
            }
        await require_membership(session, organization_id, user.id)
        account = await ensure_organization_account(session, organization_id)
        entitlement = (
            await session.execute(
                select(OrganizationEntitlement.id).where(
                    OrganizationEntitlement.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        return {
            "scope": "organization",
            "organizationId": organization_id,
            "accountId": account.id,
            "balance": await balance(session, account.id),
            "available": await available_balance(session, account.id),
            "enterprise": entitlement is not None,
        }


@router.post("/api/billing/orders", status_code=201)
async def create_order(input_data: OrderRequest, request: Request) -> dict[str, object]:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    billing = request.app.state.settings.billing
    pack = billing.pack(input_data.pack_id)
    if pack is None:
        raise APIError(400, "INVALID_PACK", "Unknown point pack")
    client = razorpay_client(billing)
    order_id = token_urlsafe(18)
    try:
        remote = await client.create_order(
            amount_paise=pack.amount_inr * 100,
            currency="INR",
            receipt=order_id,
            notes={"packId": pack.id, "points": str(pack.points)},
        )
    except RazorpayUnavailableError as error:
        raise APIError(503, "SERVICE_UNAVAILABLE", str(error)) from error
    except RazorpayError as error:
        raise APIError(502, "INTERNAL_ERROR", f"Razorpay rejected the order: {error}") from error
    async with store.sessions().begin() as session:
        if input_data.organization_id is not None:
            role = (
                await session.execute(
                    select(OrganizationMember.role).where(
                        (OrganizationMember.organization_id == input_data.organization_id)
                        & (OrganizationMember.user_id == user.id)
                    )
                )
            ).scalar_one_or_none()
            if role != "owner":
                raise APIError(404, "NOT_FOUND", "Organization not found")
            account = await ensure_organization_account(session, input_data.organization_id)
        else:
            account = await ensure_user_account(session, user.id)
        order = RazorpayOrder(
            id=order_id,
            razorpay_order_id=str(remote["id"]),
            account_id=account.id,
            purchaser_user_id=user.id,
            pack_id=pack.id,
            points=pack.points,
            amount_inr=pack.amount_inr,
        )
        session.add(order)
    return {
        "id": order.id,
        "razorpayOrderId": order.razorpay_order_id,
        "razorpayKeyId": billing.razorpay_key_id,
        "amountInr": order.amount_inr,
        "currency": order.currency,
        "packId": order.pack_id,
        "points": order.points,
    }


@router.post("/api/billing/orders/{order_id}/verify")
async def verify_checkout(
    order_id: str, input_data: VerifyCheckoutRequest, request: Request
) -> dict[str, bool]:
    """Server-side check of the browser callback signature.

    Verification never grants points by itself; only webhooks and
    reconciliation move the ledger.
    """

    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    billing = request.app.state.settings.billing
    async with store.sessions().begin() as session:
        order = await owned_order(session, order_id, user.id)
        existing = (
            await session.execute(
                select(RazorpayPayment.signature_verified).where(
                    RazorpayPayment.razorpay_payment_id == input_data.razorpay_payment_id
                )
            )
        ).scalar_one_or_none()
        if existing:
            return {"verified": True}
        if not verify_checkout_signature(
            order.razorpay_order_id,
            input_data.razorpay_payment_id,
            input_data.razorpay_signature,
            billing.razorpay_key_secret,
        ):
            raise APIError(400, "INVALID_SIGNATURE", "Checkout signature verification failed")
        await record_payment(
            session,
            order,
            payment_id=input_data.razorpay_payment_id,
            status="captured",
            method=None,
            source="checkout",
            signature_verified=True,
        )
    return {"verified": True}


@router.post("/api/billing/orders/{order_id}/reconcile")
async def reconcile_order(order_id: str, request: Request) -> dict[str, object]:
    """Pull authoritative payment state from Razorpay and apply missing grants."""

    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    billing = request.app.state.settings.billing
    client = razorpay_client(billing)
    results: list[dict[str, object]] = []
    async with store.sessions().begin() as session:
        order = await owned_order(session, order_id, user.id)
        try:
            payments = await client.order_payments(order.razorpay_order_id)
        except RazorpayUnavailableError as error:
            raise APIError(503, "SERVICE_UNAVAILABLE", str(error)) from error
        except RazorpayError as error:
            raise APIError(502, "INTERNAL_ERROR", str(error)) from error
        for payment in payments:
            payment_id = str(payment.get("id", ""))
            status = str(payment.get("status", ""))
            if not payment_id:
                continue
            row = await record_payment(
                session,
                order,
                payment_id=payment_id,
                status=status,
                method=_optional_text(payment.get("method")),
                source="reconciliation",
                signature_verified=False,
            )
            granted = await apply_grant_for_captured(session, order, row)
            refunded_inr = await sync_refunds(session, order, payment)
            results.append(
                {
                    "razorpayPaymentId": payment_id,
                    "status": status,
                    "pointsGranted": granted,
                    "refundedInr": refunded_inr,
                }
            )
    return {"orderId": order_id, "payments": results}


@router.get("/api/billing/ledger")
async def ledger_history(
    request: Request, organization_id: str | None = Query(default=None)
) -> list[dict[str, object]]:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions()() as session:
        if organization_id is None:
            account = await ensure_user_account(session, user.id)
        else:
            await require_owner_membership(session, organization_id, user.id)
            account = await ensure_organization_account(session, organization_id)
        entries = (
            (
                await session.execute(
                    select(PointLedgerEntry)
                    .where(PointLedgerEntry.account_id == account.id)
                    .order_by(PointLedgerEntry.created_at.desc())
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "amount": entry.amount,
            "reason": entry.reason,
            "createdAt": entry.created_at.isoformat(),
        }
        for entry in entries
    ]


@router.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request) -> dict[str, bool]:
    body = await request.body()
    billing = request.app.state.settings.billing
    if not billing.razorpay_webhook_secret:
        raise APIError(503, "SERVICE_UNAVAILABLE", "Webhooks are not configured")
    signature = request.headers.get("x-razorpay-signature", "")
    if not verify_webhook_signature(body, signature, billing.razorpay_webhook_secret):
        raise APIError(400, "INVALID_SIGNATURE", "Webhook signature verification failed")
    try:
        payload = json.loads(body)
    except ValueError as error:
        raise APIError(400, "INVALID_REQUEST", "Webhook body must be JSON") from error
    if not isinstance(payload, dict):
        raise APIError(400, "INVALID_REQUEST", "Webhook body must be a JSON object")
    event_type = str(payload.get("event", ""))
    event_id = request.headers.get("x-razorpay-event-id") or sha256(body).hexdigest()

    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        # The durable inbox absorbs retries, duplicates, and out-of-order events.
        bind = session.get_bind()
        values = {"id": event_id, "event_type": event_type, "payload": payload}
        statement = (
            sqlite_insert(RazorpayWebhookEvent).values(**values)
            if bind.dialect.name == "sqlite"
            else postgres_insert(RazorpayWebhookEvent).values(**values)
        ).on_conflict_do_nothing(index_elements=["id"])
        inserted = ((await session.execute(statement)).rowcount or 0) > 0
        if not inserted:
            return {"received": True}
        await process_webhook_event(session, event_type, payload)
    return {"received": True}


async def process_webhook_event(
    session: AsyncSession, event_type: str, payload: dict[str, object]
) -> None:
    payment = payment_entity(payload)
    payment_id = str(payment.get("id", ""))
    if not payment_id:
        return
    order = (
        await session.execute(
            select(RazorpayOrder).where(
                RazorpayOrder.razorpay_order_id == str(payment.get("order_id", ""))
            )
        )
    ).scalar_one_or_none()
    if order is None:
        return
    if event_type.startswith("payment.") or event_type.startswith("order."):
        row = await record_payment(
            session,
            order,
            payment_id=payment_id,
            status=str(payment.get("status", "")),
            method=_optional_text(payment.get("method")),
            source="webhook",
            signature_verified=True,
        )
        await apply_grant_for_captured(session, order, row)
        await sync_refunds(session, order, payment)
    elif event_type == "refund.processed":
        section = payload.get("payload")
        if isinstance(section, dict):
            refund_part = section.get("refund")
            if isinstance(refund_part, dict):
                entity = cast("dict[str, object] | None", refund_part.get("entity"))
                if entity:
                    merged = {**payment, "refunds": [entity]}
                    await record_payment(
                        session,
                        order,
                        payment_id=payment_id,
                        status=str(payment.get("status", "")),
                        method=_optional_text(payment.get("method")),
                        source="webhook",
                        signature_verified=True,
                    )
                    await sync_refunds(session, order, merged)


async def owned_order(
    session: AsyncSession, order_id: str, purchaser_user_id: str
) -> RazorpayOrder:
    order = (
        await session.execute(
            select(RazorpayOrder).where(
                (RazorpayOrder.id == order_id)
                & (RazorpayOrder.purchaser_user_id == purchaser_user_id)
            )
        )
    ).scalar_one_or_none()
    if order is None:
        raise APIError(404, "NOT_FOUND", "Order not found")
    return order


async def record_payment(
    session: AsyncSession,
    order: RazorpayOrder,
    *,
    payment_id: str,
    status: str,
    method: str | None,
    source: str,
    signature_verified: bool,
) -> RazorpayPayment:
    existing = (
        await session.execute(
            select(RazorpayPayment).where(
                RazorpayPayment.razorpay_payment_id == payment_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if status:
            existing.status = status
        existing.method = existing.method or method
        existing.updated_at = datetime.now(UTC)
        return existing
    payment = RazorpayPayment(
        id=token_urlsafe(18),
        razorpay_payment_id=payment_id,
        order_row_id=order.id,
        status=status or "created",
        method=method,
        amount_inr=order.amount_inr,
        source=source,
        signature_verified=signature_verified,
    )
    session.add(payment)
    session.flush()
    return payment


async def apply_grant_for_captured(
    session: AsyncSession, order: RazorpayOrder, payment: RazorpayPayment
) -> bool:
    """Grant pack points once per captured payment; idempotent by payment id."""

    if payment.status not in {"captured", "authorized"} or payment.points_granted:
        return False
    await grant_in_session(
        session,
        order.account_id,
        order.points,
        f"Razorpay purchase {order.pack_id}",
        f"purchase:{payment.razorpay_payment_id}",
    )
    payment.points_granted = True
    order.status = "paid"
    order.updated_at = datetime.now(UTC)
    return True


async def sync_refunds(
    session: AsyncSession, order: RazorpayOrder, payment_payload: dict[str, object]
) -> int:
    """Apply compensating point entries for refunds, proportional to money back."""

    refunds = payment_payload.get("refunds")
    if not isinstance(refunds, list):
        return 0
    total_refunded = 0
    for refund in refunds:
        if not isinstance(refund, dict):
            continue
        refund_id = str(refund.get("id", ""))
        amount_paise = refund.get("amount")
        if not refund_id or not isinstance(amount_paise, int):
            continue
        entry_key = f"refund:{refund_id}"
        already_applied = (
            await session.execute(
                select(PointLedgerEntry.id).where(
                    (PointLedgerEntry.account_id == order.account_id)
                    & (PointLedgerEntry.idempotency_key == entry_key)
                )
            )
        ).scalar_one_or_none()
        if already_applied is not None:
            continue
        amount_inr = amount_paise // 100
        points_back = -(-order.points * amount_inr // order.amount_inr)
        session.add(
            PointLedgerEntry(
                id=token_urlsafe(18),
                account_id=order.account_id,
                amount=-points_back,
                reason=f"Razorpay refund {order.pack_id}",
                idempotency_key=entry_key,
            )
        )
        total_refunded += amount_inr
    if total_refunded:
        payment_row = (
            await session.execute(
                select(RazorpayPayment).where(
                    (RazorpayPayment.order_row_id == order.id)
                    & (
                        RazorpayPayment.razorpay_payment_id
                        == str(payment_payload.get("id", ""))
                    )
                )
            )
        ).scalar_one_or_none()
        if payment_row is not None:
            payment_row.refunded_inr += total_refunded
            payment_row.updated_at = datetime.now(UTC)
        if payment_row is None or payment_row.refunded_inr >= order.amount_inr:
            order.status = "refunded"
            order.updated_at = datetime.now(UTC)
    return total_refunded


@router.post("/api/admin/organizations/{organization_id}/entitlement", status_code=201)
async def provision_entitlement(
    organization_id: str, input_data: EntitlementRequest, request: Request
) -> dict[str, object]:
    session = await admin_session(request)
    try:
        existing = (
            await session.execute(
                select(OrganizationEntitlement).where(
                    OrganizationEntitlement.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise APIError(409, "INVALID_REQUEST", "Entitlement already exists") from None
        entitlement = OrganizationEntitlement(
            id=token_urlsafe(18),
            organization_id=organization_id,
            provisioned_by="admin",
            note=input_data.note.strip() or None,
        )
        session.add(entitlement)
        await session.commit()
    finally:
        await session.close()
    return {"organizationId": organization_id, "note": entitlement.note}


@router.delete(
    "/api/admin/organizations/{organization_id}/entitlement", status_code=204
)
async def revoke_entitlement(organization_id: str, request: Request) -> None:
    session = await admin_session(request)
    try:
        result = await session.execute(
            select(OrganizationEntitlement).where(
                OrganizationEntitlement.organization_id == organization_id
            )
        )
        entitlement = result.scalar_one_or_none()
        if entitlement is None:
            await session.rollback()
            raise APIError(404, "NOT_FOUND", "Entitlement not found") from None
        await session.delete(entitlement)
        await session.commit()
    finally:
        await session.close()


async def admin_session(request: Request) -> AsyncSession:
    """Administrative endpoints authenticate through a shared operator token."""

    settings = request.app.state.settings
    token = request.headers.get("x-admin-token", "")
    if not settings.billing.admin_token or token != settings.billing.admin_token:
        raise APIError(404, "NOT_FOUND", "Not found") from None
    store = require_sqlalchemy_store(request)
    return store.sessions()()


def razorpay_client(billing) -> RazorpayClient:
    try:
        return RazorpayClient(billing.razorpay_key_id, billing.razorpay_key_secret)
    except RazorpayUnavailableError as error:
        raise APIError(503, "SERVICE_UNAVAILABLE", str(error)) from error


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


async def require_owner_membership(
    session: AsyncSession, organization_id: str, user_id: str
) -> None:
    role = (
        await session.execute(
            select(OrganizationMember.role).where(
                (OrganizationMember.organization_id == organization_id)
                & (OrganizationMember.user_id == user_id)
            )
        )
    ).scalar_one_or_none()
    if role != "owner":
        raise APIError(404, "NOT_FOUND", "Organization not found")


# Quote kinds are referenced by tests and clients; keep them importable here.
__all__ = ["router", "INDEPENDENT_QUOTE", "EMPLOYER_QUOTE"]
