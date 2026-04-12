import asyncio
from typing import Any

import stripe
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

logger = structlog.get_logger(__name__)
settings = get_settings()

stripe.api_key = settings.STRIPE_SECRET_KEY

TIER_BY_PRICE: dict[str, str] = {
    settings.STRIPE_PRICE_PRO: "pro",
    settings.STRIPE_PRICE_TEAM: "team",
}


class StripeService:
    async def create_checkout_session(
        self,
        user: User,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout session and return the session URL."""
        customer_id = user.stripe_customer_id

        if not customer_id:
            customer = await asyncio.to_thread(
                stripe.Customer.create,
                email=user.email,
                metadata={"user_id": str(user.id)},
            )
            customer_id = customer.id

        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user.id)},
        )
        return session.url or ""

    async def create_portal_session(self, customer_id: str, return_url: str) -> str:
        session = await asyncio.to_thread(
            stripe.billing_portal.Session.create,
            customer=customer_id,
            return_url=return_url,
        )
        return str(session.url or "")

    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str,
        db: AsyncSession,
    ) -> None:
        try:
            event = await asyncio.to_thread(
                stripe.Webhook.construct_event,
                payload,
                sig_header,
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except stripe.error.SignatureVerificationError:
            logger.warning("Invalid Stripe webhook signature")
            raise ValueError("Invalid Stripe signature")

        event_type: str = event["type"]
        logger.info("Stripe webhook received", event_type=event_type)

        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(event["data"]["object"], db)
        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            await self._handle_subscription_change(event["data"]["object"], db)

    async def _handle_checkout_completed(
        self, session: dict[str, Any], db: AsyncSession
    ) -> None:
        user_id: str = session["metadata"]["user_id"]
        customer_id: str = session["customer"]
        subscription_id: str = session["subscription"]

        subscription = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
        price_id: str = subscription["items"]["data"][0]["price"]["id"]
        tier = TIER_BY_PRICE.get(price_id, "free")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.stripe_customer_id = customer_id
            user.subscription_tier = tier
            logger.info("Subscription activated", user_id=user_id, tier=tier)

    async def _handle_subscription_change(
        self, subscription: dict[str, Any], db: AsyncSession
    ) -> None:
        customer_id: str = subscription["customer"]
        status: str = subscription["status"]

        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        if status in ("canceled", "unpaid", "incomplete_expired"):
            user.subscription_tier = "free"
            logger.info("Subscription downgraded to free", customer_id=customer_id)
        elif status == "active":
            price_id = subscription["items"]["data"][0]["price"]["id"]
            tier = TIER_BY_PRICE.get(price_id, "free")
            user.subscription_tier = tier
            logger.info("Subscription updated", customer_id=customer_id, tier=tier)
