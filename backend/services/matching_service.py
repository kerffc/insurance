"""Deterministic client-to-policy-change matching."""


def match_clients(clients: list[dict], change: dict) -> list[dict]:
    """Return clients affected by the given policy change."""
    matched = []
    change_insurer = change["insurer"].strip().lower()
    change_line = change.get("product_line", "").strip().lower()
    change_plans = [p.strip().lower() for p in change.get("plan_names", []) if p.strip()]

    for client in clients:
        if client["insurer"].strip().lower() != change_insurer:
            continue

        # "All" product line matches everything from this insurer
        if change_line == "all":
            matched.append(client)
            continue

        if client["policy_type"].strip().lower() != change_line:
            continue

        # If specific plans listed, check plan match
        if change_plans:
            client_plan = (client.get("plan_name") or "").strip().lower()
            if client_plan and client_plan in change_plans:
                matched.append(client)
        else:
            # No specific plans = all plans in this product line
            matched.append(client)

    return matched
