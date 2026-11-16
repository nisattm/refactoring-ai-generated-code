"""Two identical blocks (duplication, jscpd --min-lines 5 --min-tokens 50)."""


def total_a(rows):
    result = []
    for row in rows:
        if row["amount"] > 0 and row["status"] == "open":
            result.append({"id": row["id"], "amount": row["amount"], "label": str(row["id"]).zfill(8)})
        elif row["status"] == "paid":
            result.append({"id": row["id"], "amount": 0, "label": str(row["id"]).zfill(8)})
    return sorted(result, key=lambda item: (item["amount"], item["id"]))


def total_b(rows):
    result = []
    for row in rows:
        if row["amount"] > 0 and row["status"] == "open":
            result.append({"id": row["id"], "amount": row["amount"], "label": str(row["id"]).zfill(8)})
        elif row["status"] == "paid":
            result.append({"id": row["id"], "amount": 0, "label": str(row["id"]).zfill(8)})
    return sorted(result, key=lambda item: (item["amount"], item["id"]))
