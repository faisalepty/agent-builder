# omnis_hermes/tools/internal/transaction_tools.py
from tools.decorator import tool

@tool(
    name="fetch_transaction_status",
    description="Look up a transaction's current status in the ledger.",
    param_descriptions={"tx_id": "Unique transaction ID, e.g. TX_001"},
)
def fetch_transaction_status(tx_id: str) -> str:
    # Replace with actual ledger/API call
    # Simulated response for testing:
    statuses = {"TX_001": "completed", "TX_002": "pending", "TX_003": "failed"}
    return statuses.get(tx_id, f"Transaction '{tx_id}' not found")