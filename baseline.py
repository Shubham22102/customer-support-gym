import asyncio
import argparse
import re

from client import SupportEnv, make_action
from models import ActionType


class RuleBasedAgent:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.step = 0
        self.order_ids = []
        self.amounts = []
        self.fraud_flagged = False
        self.actions_queue = []

    def _init_queue(self, obs):
        msg = getattr(obs, "observation", "") or ""
        if hasattr(obs, "metadata") and getattr(obs, "metadata", None) and "opening_message" in obs.metadata:
            msg += " " + obs.metadata["opening_message"]

        self.order_ids = re.findall(r"ORD-[A-Z0-9]+", msg)

        if not self.order_ids:
            if hasattr(obs, "ticket_state") and getattr(obs, "ticket_state", None):
                history = getattr(obs.ticket_state, "message_history", [])
                if history:
                    msg += " ".join([getattr(m, "content", "") for m in history])
            self.order_ids = re.findall(r"ORD-[A-Z0-9]+", msg)

        if self.task_id == "easy_refund":
            self.actions_queue.append(
                ("lookup_order", {"order_id": self.order_ids[0] if self.order_ids else "ORD-000"}))
            self.actions_queue.append(("check_policy", {"policy_id": "POL-REFUND-001"}))
            self.actions_queue.append(
                ("issue_refund", {"amount": "{total_amount}", "refund_type": "full", "reason": "Customer received wrong item"}))
            self.actions_queue.append(
                ("close_ticket", {"resolution": "refund_issued", "summary": "Full refund issued for wrong item received."}))

        elif self.task_id == "billing_dispute":
            self.actions_queue.append(
                ("lookup_order", {"order_id": self.order_ids[0] if self.order_ids else "ORD-000"}))
            if len(self.order_ids) > 1:
                self.actions_queue.append(("lookup_order", {"order_id": self.order_ids[1]}))
            else:
                self.actions_queue.append(("check_policy", {"policy_id": "POL-REFUND-001"}))
            self.actions_queue.append(("check_policy", {"policy_id": "POL-FRAUD-001"}))
            self.actions_queue.append(
                ("request_info", {"info_type": "transaction_id", "message": "Please confirm which charge is the duplicate."}))
            self.actions_queue.append(
                ("issue_refund", {"amount": "{min_amount}", "refund_type": "partial", "reason": "Duplicate charge refunded"}))
            self.actions_queue.append(
                ("close_ticket", {"resolution": "partial_refund_issued", "summary": "Partial refund issued for duplicate charge."}))

        elif self.task_id == "multi_issue":
            self.actions_queue.append(
                ("lookup_order", {"order_id": self.order_ids[0] if self.order_ids else "ORD-000"}))
            self.actions_queue.append(("check_policy", {"policy_id": "POL-FRAUD-001"}))
            self.actions_queue.append(("conditional_escalate", {}))
            self.actions_queue.append(
                ("request_info", {"info_type": "account_details", "message": "Please confirm your name and email for identity verification."}))
            if len(self.order_ids) > 1:
                self.actions_queue.append(("lookup_order", {"order_id": self.order_ids[1]}))
            self.actions_queue.append(
                ("send_message", {"message_type": "update", "message": "I am investigating all three issues you raised and will resolve them now."}))
            self.actions_queue.append(
                ("issue_refund", {"amount": "{non_fraud_amount}", "refund_type": "full", "reason": "Refund for late delivery"}))
            self.actions_queue.append(
                ("send_message", {"message_type": "confirmation", "message": "Your account has been unlocked following identity verification."}))
            self.actions_queue.append(
                ("close_ticket", {"resolution": "multiple_resolutions", "summary": "Account unlocked, fraud escalated, refund issued for late delivery."}))

    def act(self, obs):
        if self.step == 0:
            self._init_queue(obs)

        if obs and getattr(obs, "tool_result", None) is not None:
            res = obs.tool_result
            if "total_amount" in res:
                self.amounts.append(float(res["total_amount"]))
            elif "order_details" in res and "total_amount" in res["order_details"]:
                self.amounts.append(float(res["order_details"]["total_amount"]))

            if res.get("fraud_flagged") is True or res.get("is_fraud") is True:
                self.fraud_flagged = True

        self.step += 1

        if not self.actions_queue:
            return make_action(ActionType("close_ticket"), resolution="unresolved", summary="No more actions")

        action_name, params = self.actions_queue.pop(0)

        while action_name == "conditional_escalate":
            if self.fraud_flagged:
                return make_action(
                    ActionType("escalate"),
                    reason="potential_fraud",
                    team="fraud_investigation",
                    notes="Unauthorized transaction detected. Escalating per POL-FRAUD-001."
                )
            if not self.actions_queue:
                return make_action(ActionType("close_ticket"), resolution="unresolved", summary="No more actions")
            action_name, params = self.actions_queue.pop(0)

        if "amount" in params:
            if params["amount"] == "{total_amount}":
                params["amount"] = self.amounts[0] if self.amounts else 0.0
            elif params["amount"] == "{min_amount}":
                params["amount"] = min(self.amounts) if self.amounts else 0.0
            elif params["amount"] == "{non_fraud_amount}":
                params["amount"] = self.amounts[-1] if self.amounts else 0.0

        return make_action(ActionType(action_name), **params)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    tasks = ["easy_refund", "billing_dispute", "multi_issue"]
    results = []

    for task_id in tasks:
        async with SupportEnv(base_url=args.base_url) as env:
            obs = await env.reset(task_id=task_id)
            agent = RuleBasedAgent(task_id=task_id)
            done = False
            reward = 0.0
            steps = 0
            resolution = "unknown"

            while not done:
                action = agent.act(obs)
                result = await env.step(action)
                obs = result.observation
                done = result.done
                reward = result.reward
                steps += 1
                if done:
                    resolution = obs.tool_result.get("resolution", "timeout") if obs.tool_result else "timeout"

            results.append((task_id, round(reward, 4), steps, obs.max_steps, resolution))

    # Print score table
    print("\nCustomer Support Resolution Gym — Baseline Scores")
    print("=" * 60)
    print(f"{'Task':<22} {'Score':<10} {'Steps':<12} {'Result'}")
    print("-" * 60)
    for task_id, score, steps, max_steps, resolution in results:
        print(f"{task_id:<22} {score:<10} {str(steps)+'/'+str(max_steps):<12} {resolution}")
    print("-" * 60)
    mean = sum(r[1] for r in results) / len(results)
    print(f"Mean score: {round(mean, 4)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
