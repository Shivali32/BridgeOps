import os
from uuid import UUID

import httpx


class ProviderError(Exception):
    def __init__(self, category: str, message: str, *, unknown=False, retryable=False):
        super().__init__(message)
        self.category = category
        self.unknown = unknown
        self.retryable = retryable


class Providers:
    """Explicit synchronous HTTP boundary, shared by routes and future workers."""

    def __init__(self, transport=None):
        self.inventory = os.getenv("INVENTORY_URL", "http://127.0.0.1:8001")
        self.fulfillment = os.getenv("FULFILLMENT_URL", "http://127.0.0.1:8002")
        self.timeout = float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "3"))
        self.transport = transport

    def call(self, step: str, payload: dict):
        base, path = {
            "inventory_check": (self.inventory, "/inventory/check"),
            "inventory_reservation": (self.inventory, "/inventory/reservations"),
            "fulfillment_request": (self.fulfillment, "/fulfillment/requests"),
        }[step]
        mutation = step != "inventory_check"
        try:
            with httpx.Client(
                timeout=self.timeout, trust_env=False, transport=self.transport
            ) as client:
                response = client.post(base + path, json=payload)
        except httpx.RequestError:
            raise ProviderError(
                "timeout_unknown" if mutation else "provider_unavailable",
                "Provider response unavailable. Reconcile before retrying."
                if mutation
                else "Inventory check unavailable.",
                unknown=mutation,
                retryable=True,
            ) from None
        if response.status_code >= 400:
            category = "provider_rejected"
            if response.status_code >= 500:
                category = "provider_unavailable"
            elif step == "inventory_reservation" and response.status_code == 409:
                try:
                    if (
                        response.json().get("detail", {}).get("code")
                        == "insufficient_stock"
                    ):
                        category = "insufficient_stock"
                except (ValueError, TypeError, AttributeError):
                    pass
            elif response.status_code in (401, 403):
                category = "authorization_error"
            raise ProviderError(
                category,
                f"Provider returned HTTP {response.status_code}.",
                retryable=response.status_code >= 500
                or category == "insufficient_stock",
            )
        try:
            result = response.json()
            if step == "inventory_check":
                if type(result["available"]) is not bool:
                    raise ValueError
                if not result["available"]:
                    missing = any(
                        i.get("available") is None for i in result.get("items", [])
                    )
                    raise ProviderError(
                        "validation_error" if missing else "insufficient_stock",
                        "Unknown SKU." if missing else "Insufficient stock.",
                        retryable=not missing,
                    )
            else:
                UUID(result["id"])
                expected_status = (
                    "reserved" if step == "inventory_reservation" else "accepted"
                )
                if (
                    result["tenant_id"] != payload["tenant_id"]
                    or result["idempotency_key"] != payload["idempotency_key"]
                    or result["status"] != expected_status
                ):
                    raise ValueError
            return result
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError(
                "timeout_unknown" if mutation else "provider_rejected",
                "Invalid provider response.",
                unknown=mutation,
                retryable=mutation,
            ) from None

    def lookup(self, step: str, payload: dict, reference=None):
        from urllib.parse import quote

        base, path = (
            (self.inventory, "/inventory/reservations")
            if step == "inventory_reservation"
            else (self.fulfillment, "/fulfillment/requests")
        )
        suffix = (
            "/" + str(reference)
            if reference
            else "/by-key/" + quote(payload["idempotency_key"], safe="")
        )
        try:
            with httpx.Client(
                timeout=self.timeout, trust_env=False, transport=self.transport
            ) as client:
                response = client.get(
                    base + path + suffix, params={"tenant_id": payload["tenant_id"]}
                )
        except httpx.RequestError:
            raise ProviderError(
                "timeout_unknown",
                "Provider reconciliation unavailable; outcome remains uncertain.",
                unknown=True,
                retryable=True,
            ) from None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ProviderError(
                "provider_unavailable",
                f"Reconciliation returned HTTP {response.status_code}.",
                unknown=True,
                retryable=True,
            )
        try:
            result = response.json()
            UUID(result["id"])
            expected = "reserved" if step == "inventory_reservation" else "accepted"
            if (
                result["tenant_id"] != payload["tenant_id"]
                or result["idempotency_key"] != payload["idempotency_key"]
                or result["status"] != expected
            ):
                raise ValueError
            if sorted(result["items"], key=lambda i: i["sku"]) != sorted(
                payload["items"], key=lambda i: i["sku"]
            ):
                raise ValueError
            if step == "fulfillment_request" and any(
                result[k] != payload[k] for k in ("order_id", "reservation_id")
            ):
                raise ValueError
            return result
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError(
                "provider_rejected",
                "Provider reference does not match this operation.",
                unknown=True,
            ) from None


def get_providers():
    return Providers()
