from __future__ import annotations
import secrets
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import aiosqlite
from models import (
    SupportAction, TicketState, ActionType, EpisodeConfig,
    RefundRecord, EscalationRecord,
    OrderRecord, OrderItem, ShippingAddress, CustomerRecord,
    InfoType, MessageType, EscalationReason, EscalationTeam,
    RefundType, ResolutionType, PolicyRule, KBArticle, IssueType, OrderStatus
)


@dataclass
class ToolResult:
    tool_result: dict[str, Any]
    sentiment_delta: float = 0.0
    state_mutations: dict[str, Any] = field(default_factory=dict)


class ToolRouter:
    def __init__(self, policies: dict[str, PolicyRule], kb_articles: list[KBArticle]) -> None:
        self._policies = policies      # keyed by policy_id
        self._kb_articles = kb_articles

    async def execute(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        episode_config: EpisodeConfig,
    ) -> ToolResult:
        handlers = {
            ActionType.LOOKUP_ORDER:  self._handle_lookup_order,
            ActionType.CHECK_POLICY:  self._handle_check_policy,
            ActionType.SEARCH_KB:     self._handle_search_kb,
            ActionType.REQUEST_INFO:  self._handle_request_info,
            ActionType.ISSUE_REFUND:  self._handle_issue_refund,
            ActionType.SEND_MESSAGE:  self._handle_send_message,
            ActionType.ESCALATE:      self._handle_escalate,
            ActionType.CLOSE_TICKET:  self._handle_close_ticket,
        }
        handler = handlers.get(action.action_type)
        if handler is None:
            return ToolResult(tool_result={"error": f"Unknown action type: {action.action_type}"})
        return await handler(action, state, db, episode_config)

    # ------------------------------------------------------------------
    # Handler: LOOKUP_ORDER
    # ------------------------------------------------------------------

    async def _handle_lookup_order(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            order_id = action.parameters.get("order_id")
            if not order_id:
                return ToolResult(tool_result={"error": "Missing required parameter: order_id"})

            # Query order
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return ToolResult(tool_result={"error": f"Order {order_id} not found"})

            order = dict(row)
            # fraud_flagged is stored as INTEGER 0/1
            fraud_flagged = bool(order.get("fraud_flagged", 0))

            # Customer ownership check
            if state.customer_id and order["customer_id"] != state.customer_id:
                return ToolResult(
                    tool_result={
                        "error": (
                            f"Order {order_id} does not belong to the current customer"
                        )
                    }
                )

            # Query order items
            async with db.execute(
                "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
            ) as cursor:
                item_rows = await cursor.fetchall()

            items = [dict(r) for r in item_rows]

            # Build full order dict
            order_dict = {
                "order_id": order["order_id"],
                "customer_id": order["customer_id"],
                "status": order["status"],
                "total_amount": order["total_amount"],
                "payment_method": order["payment_method"],
                "created_at": order["created_at"],
                "shipped_at": order["shipped_at"],
                "delivered_at": order["delivered_at"],
                "tracking_number": order["tracking_number"],
                "fraud_flagged": fraud_flagged,
                "shipping_address": {
                    "street": order["street"],
                    "city": order["city"],
                    "state": order["state"],
                    "zip": order["zip"],
                    "country": order["country"],
                },
                "items": items,
            }

            state_mutations: dict[str, Any] = {}
            if fraud_flagged:
                state_mutations["fraud_flag"] = True

            return ToolResult(
                tool_result=order_dict,
                sentiment_delta=0.0,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: CHECK_POLICY
    # ------------------------------------------------------------------

    async def _handle_check_policy(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            policy_id = action.parameters.get("policy_id")
            if not policy_id:
                return ToolResult(tool_result={"error": "Missing required parameter: policy_id"})

            policy = self._policies.get(policy_id)
            if policy is None:
                return ToolResult(tool_result={"error": f"Policy {policy_id} not found"})

            # Append to policies_checked
            existing: list[str] = list(state.policies_checked)
            if policy_id not in existing:
                existing.append(policy_id)

            state_mutations: dict[str, Any] = {"policies_checked": existing}

            policy_dict = policy.model_dump()

            return ToolResult(
                tool_result=policy_dict,
                sentiment_delta=0.0,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: SEARCH_KB
    # ------------------------------------------------------------------

    async def _handle_search_kb(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            query = action.parameters.get("query", "")
            if not query or len(query) < 5:
                return ToolResult(
                    tool_result={"error": "Parameter 'query' must be at least 5 characters"}
                )

            words = query.lower().split()

            scored: list[tuple[int, KBArticle]] = []
            for article in self._kb_articles:
                haystack = (article.title + " " + article.content).lower()
                score = sum(1 for w in words if w in haystack)
                if score > 0:
                    scored.append((score, article))

            if not scored:
                return ToolResult(
                    tool_result={"results": [], "message": "No articles found"},
                    sentiment_delta=0.0,
                )

            scored.sort(key=lambda x: x[0], reverse=True)
            top3 = [a.model_dump() for _, a in scored[:3]]

            return ToolResult(
                tool_result={"results": top3},
                sentiment_delta=0.0,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: REQUEST_INFO
    # ------------------------------------------------------------------

    async def _handle_request_info(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            message = action.parameters.get("message", "")
            if not message or len(message) < 10:
                return ToolResult(
                    tool_result={"error": "Parameter 'message' must be at least 10 characters"}
                )

            info_type_value = action.parameters.get("info_type")
            if not info_type_value:
                return ToolResult(tool_result={"error": "Missing required parameter: info_type"})

            try:
                info_type = InfoType(info_type_value)
            except ValueError:
                return ToolResult(
                    tool_result={"error": f"Invalid info_type: {info_type_value}"}
                )

            # Look up canned reply
            reply_text = config.customer_replies.get(
                info_type.value,
                "I'm not sure I understand what you need.",
            )

            state_mutations: dict[str, Any] = {
                "info_requested": True,
                "info_type_requested": info_type,
                "customer_message": reply_text,
            }

            return ToolResult(
                tool_result={"customer_reply": reply_text},
                sentiment_delta=0.05,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: ISSUE_REFUND
    # ------------------------------------------------------------------

    async def _handle_issue_refund(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            order_id = action.parameters.get("order_id")
            amount_raw = action.parameters.get("amount")
            reason = action.parameters.get("reason", "")
            refund_type_value = action.parameters.get("refund_type")

            # Validate presence
            if not order_id:
                return ToolResult(tool_result={"error": "Missing required parameter: order_id"})
            if amount_raw is None:
                return ToolResult(tool_result={"error": "Missing required parameter: amount"})
            if not reason:
                return ToolResult(tool_result={"error": "Missing required parameter: reason"})
            if not refund_type_value:
                return ToolResult(tool_result={"error": "Missing required parameter: refund_type"})

            # Validate types
            try:
                amount = float(amount_raw)
            except (TypeError, ValueError):
                return ToolResult(tool_result={"error": "Parameter 'amount' must be a number"})

            if amount <= 0:
                return ToolResult(tool_result={"error": "Parameter 'amount' must be greater than 0"})

            try:
                refund_type = RefundType(refund_type_value)
            except ValueError:
                return ToolResult(tool_result={"error": f"Invalid refund_type: {refund_type_value}"})

            # Query order
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row is None:
                return ToolResult(tool_result={"error": f"Order {order_id} not found"})

            order = dict(row)
            total_amount = float(order["total_amount"])
            fraud_flagged = bool(order.get("fraud_flagged", 0))
            delivered_at = order.get("delivered_at")

            # Amount exceeds order total check
            if amount > total_amount:
                return ToolResult(
                    tool_result={
                        "error": f"Refund amount exceeds order total of ${total_amount:.2f}"
                    }
                )

            # Policy violation tracking
            policy_violations: list[str] = list(state.policy_violations)
            sentiment_delta = 0.0
            policy_violated = False

            # POL-FRAUD-001: fraud-flagged order
            if fraud_flagged:
                if "POL-FRAUD-001" not in policy_violations:
                    policy_violations.append("POL-FRAUD-001")
                policy_violated = True
                sentiment_delta = -0.20

            # POL-FRAUD-002: amount > 500 and not already escalated
            if amount > 500.0 and not state.escalated:
                if "POL-FRAUD-002" not in policy_violations:
                    policy_violations.append("POL-FRAUD-002")
                policy_violated = True
                sentiment_delta = -0.20

            # POL-REFUND-002 / POL-REFUND-003: delivery window checks
            if delivered_at:
                try:
                    delivered_dt = datetime.fromisoformat(
                        delivered_at.replace("Z", "+00:00")
                    )
                    now = datetime.now(timezone.utc)
                    # Make delivered_dt timezone-aware if it isn't
                    if delivered_dt.tzinfo is None:
                        delivered_dt = delivered_dt.replace(tzinfo=timezone.utc)
                    days_since_delivery = (now - delivered_dt).days

                    # POL-REFUND-003: > 90 days
                    if days_since_delivery > 90:
                        if "POL-REFUND-003" not in policy_violations:
                            policy_violations.append("POL-REFUND-003")
                        policy_violated = True
                        sentiment_delta = -0.20
                    else:
                        # POL-REFUND-002: late return window + full refund
                        # Determine category from order items to find the return window
                        async with db.execute(
                            """
                            SELECT p.category FROM order_items oi
                            JOIN products p ON oi.sku = p.sku
                            WHERE oi.order_id = ?
                            LIMIT 1
                            """,
                            (order_id,),
                        ) as cursor:
                            cat_row = await cursor.fetchone()

                        category = dict(cat_row)["category"] if cat_row else None

                        if category in ("electronics", "home_goods"):
                            window = 30
                        elif category == "apparel":
                            window = 60
                        else:
                            window = 30  # default

                        if days_since_delivery > window and refund_type == RefundType.FULL:
                            if "POL-REFUND-002" not in policy_violations:
                                policy_violations.append("POL-REFUND-002")
                            policy_violated = True
                            sentiment_delta = -0.20
                except Exception:
                    pass  # If date parsing fails, skip window checks

            # Generate refund record
            refund_id = "REF-" + secrets.token_hex(3).upper()
            now_iso = datetime.now(timezone.utc).isoformat()

            await db.execute(
                """
                INSERT INTO refunds
                    (refund_id, order_id, customer_id, amount, refund_type, reason, status, eta_days, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    refund_id,
                    order_id,
                    order["customer_id"],
                    round(amount, 2),
                    refund_type.value,
                    reason,
                    "processed",
                    5,
                    now_iso,
                ),
            )
            await db.commit()

            # Compute sentiment delta based on refund ratio (only if no policy violation)
            if not policy_violated:
                ratio = amount / total_amount if total_amount > 0 else 0.0
                if ratio >= 0.95:
                    sentiment_delta = 0.20
                elif ratio >= 0.45:
                    sentiment_delta = 0.10
                else:
                    sentiment_delta = 0.02

            state_mutations: dict[str, Any] = {
                "refund_issued": True,
                "refund_amount": round(amount, 2),
                "refund_order_id": order_id,
            }
            if policy_violations != list(state.policy_violations):
                state_mutations["policy_violations"] = policy_violations

            return ToolResult(
                tool_result={
                    "refund_id": refund_id,
                    "amount": round(amount, 2),
                    "status": "processed",
                    "eta_days": 5,
                },
                sentiment_delta=sentiment_delta,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: SEND_MESSAGE
    # ------------------------------------------------------------------

    async def _handle_send_message(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            message = action.parameters.get("message", "")
            if not message or len(message) < 10:
                return ToolResult(
                    tool_result={"error": "Parameter 'message' must be at least 10 characters"}
                )

            message_type_value = action.parameters.get("message_type")
            if not message_type_value:
                return ToolResult(
                    tool_result={"error": "Missing required parameter: message_type"}
                )

            try:
                message_type = MessageType(message_type_value)
            except ValueError:
                return ToolResult(
                    tool_result={"error": f"Invalid message_type: {message_type_value}"}
                )

            msg_count = len(state.messages_sent)

            # Base sentiment delta by message type
            base_deltas = {
                MessageType.APOLOGY: 0.08,
                MessageType.UPDATE: 0.05,
                MessageType.EXPLANATION: 0.04,
                MessageType.CONFIRMATION: 0.06,
                MessageType.CLOSING: 0.03,
            }
            base = base_deltas.get(message_type, 0.03)

            if msg_count > 3:
                base = base * 0.3

            # Empathy bonus
            empathy_words = [
                "apologize", "sorry", "understand", "frustrating",
                "appreciate", "patience", "priority",
            ]
            if any(w in message.lower() for w in empathy_words):
                base += 0.03

            sentiment_delta = round(min(base, 0.12), 4)

            # Append message to messages_sent
            messages_sent = list(state.messages_sent) + [message]
            state_mutations: dict[str, Any] = {"messages_sent": messages_sent}

            # Special: confirmation + account_details info type → resolve ACCOUNT_LOCKED
            if (
                message_type == MessageType.CONFIRMATION
                and state.info_type_requested == InfoType.ACCOUNT_DETAILS
            ):
                issues_resolved = list(state.issues_resolved)
                if IssueType.ACCOUNT_LOCKED not in issues_resolved:
                    issues_resolved.append(IssueType.ACCOUNT_LOCKED)
                state_mutations["issues_resolved"] = issues_resolved

            return ToolResult(
                tool_result={
                    "delivered": True,
                    "sentiment_impact": f"+{sentiment_delta}",
                },
                sentiment_delta=sentiment_delta,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: ESCALATE
    # ------------------------------------------------------------------

    async def _handle_escalate(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            reason_value = action.parameters.get("reason")
            team_value = action.parameters.get("team")
            notes = action.parameters.get("notes", "")

            if not reason_value:
                return ToolResult(tool_result={"error": "Missing required parameter: reason"})
            if not team_value:
                return ToolResult(tool_result={"error": "Missing required parameter: team"})
            if not notes or len(notes) < 20:
                return ToolResult(
                    tool_result={"error": "Parameter 'notes' must be at least 20 characters"}
                )

            try:
                reason = EscalationReason(reason_value)
            except ValueError:
                return ToolResult(
                    tool_result={"error": f"Invalid escalation reason: {reason_value}"}
                )

            try:
                team = EscalationTeam(team_value)
            except ValueError:
                return ToolResult(
                    tool_result={"error": f"Invalid escalation team: {team_value}"}
                )

            escalation_id = "ESC-" + secrets.token_hex(3).upper()
            now_iso = datetime.now(timezone.utc).isoformat()

            await db.execute(
                """
                INSERT INTO escalations
                    (escalation_id, ticket_id, reason, team, notes, status, eta_hours, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    escalation_id,
                    state.ticket_id,
                    reason.value,
                    team.value,
                    notes,
                    "submitted",
                    24,
                    now_iso,
                ),
            )
            await db.commit()

            state_mutations: dict[str, Any] = {
                "escalated": True,
                "escalation_team": team,
                "escalation_reason": reason,
            }

            # Determine which issue this escalation resolves
            issues_resolved = list(state.issues_resolved)
            if reason == EscalationReason.POTENTIAL_FRAUD:
                if IssueType.UNAUTHORIZED_TRANSACTION not in issues_resolved:
                    issues_resolved.append(IssueType.UNAUTHORIZED_TRANSACTION)
            state_mutations["issues_resolved"] = issues_resolved

            return ToolResult(
                tool_result={
                    "escalation_id": escalation_id,
                    "team": team.value,
                    "eta_hours": 24,
                    "status": "submitted",
                },
                sentiment_delta=0.10,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})

    # ------------------------------------------------------------------
    # Handler: CLOSE_TICKET
    # ------------------------------------------------------------------

    async def _handle_close_ticket(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        config: EpisodeConfig,
    ) -> ToolResult:
        try:
            from models import TicketStatus  # local import avoids circular issues

            resolution_value = action.parameters.get("resolution")
            summary = action.parameters.get("summary", "")

            if not resolution_value:
                return ToolResult(
                    tool_result={"error": "Missing required parameter: resolution"},
                    sentiment_delta=0.0,
                    state_mutations={},
                )
            if not summary or len(summary) < 20:
                return ToolResult(
                    tool_result={"error": "Parameter 'summary' must be at least 20 characters"},
                    sentiment_delta=0.0,
                    state_mutations={},
                )

            try:
                resolution = ResolutionType(resolution_value)
            except ValueError:
                return ToolResult(
                    tool_result={"error": f"Invalid resolution: {resolution_value}"},
                    sentiment_delta=0.0,
                    state_mutations={},
                )

            state_mutations: dict[str, Any] = {
                "ticket_status": TicketStatus.CLOSED,
                "resolution": resolution,
                "resolution_summary": summary,
            }

            issues_resolved = list(state.issues_resolved)
            policy_violations = list(state.policy_violations)

            # ACCOUNT_UNLOCKED checks
            if resolution == ResolutionType.ACCOUNT_UNLOCKED:
                if IssueType.ACCOUNT_LOCKED not in issues_resolved:
                    # Check if identity verification was done
                    if not (
                        state.info_requested
                        and state.info_type_requested == InfoType.ACCOUNT_DETAILS
                    ):
                        # Skipped identity verification — policy violation
                        if "POL-ACCT-001" not in policy_violations:
                            policy_violations.append("POL-ACCT-001")
                        state_mutations["policy_violations"] = policy_violations
                    else:
                        # Verification was done, mark as resolved
                        issues_resolved.append(IssueType.ACCOUNT_LOCKED)

            # REFUND_ISSUED / PARTIAL_REFUND_ISSUED: map config issue types to resolved
            if resolution in (
                ResolutionType.REFUND_ISSUED,
                ResolutionType.PARTIAL_REFUND_ISSUED,
            ):
                refund_issue_types = {
                    IssueType.WRONG_ITEM_RECEIVED,
                    IssueType.LATE_DELIVERY,
                    IssueType.DAMAGED_ITEM,
                    IssueType.DEFECTIVE_ITEM,
                    IssueType.MISSING_PARTS,
                    IssueType.WRONG_SIZE,
                    IssueType.DUPLICATE_CHARGE,
                    IssueType.WRONG_AMOUNT,
                    IssueType.REFUND_NOT_RECEIVED,
                    IssueType.LOST_IN_TRANSIT,
                }
                for it in config.issue_types:
                    if it in refund_issue_types and it not in issues_resolved:
                        issues_resolved.append(it)

            state_mutations["issues_resolved"] = issues_resolved

            return ToolResult(
                tool_result={
                    "ticket_closed": True,
                    "resolution": resolution_value,
                    "summary": summary,
                },
                sentiment_delta=0.05,
                state_mutations=state_mutations,
            )

        except Exception as e:
            return ToolResult(tool_result={"error": str(e)})
