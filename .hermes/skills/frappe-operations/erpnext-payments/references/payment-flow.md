# ERPNext Payment Flow — End-to-End

## Status Lifecycle: Payment Request

```
Draft → Submitted (Requested) → Initiated → Paid
                                       ↓
                              Partially Paid
                                       ↓
                                   Failed
                                       → Cancelled
```

- **Draft**: Being created, not yet sent
- **Requested**: Submitted, payment URL generated, email sent (if configured)
- **Initiated**: Customer opened the payment page and started the payment process
- **Paid**: Payment confirmed, Payment Entry auto-created
- **Partially Paid**: Some amount received, remainder still outstanding
- **Failed**: Payment attempt failed (card declined, etc.)
- **Cancelled**: Manually cancelled before completion

## DocTypes Involved

| DocType | Role |
|---|---|
| **Payment Gateway Account** | Stores API keys and config for a gateway (Stripe, etc.) |
| **Payment Request** | The request sent to the customer; generates the payment URL |
| **Integration Request** | Logs webhook callbacks from the gateway |
| **Payment Entry** | Auto-created on successful payment; the actual accounting record |
| **Sales Invoice** | The invoice being paid; reconciled against Payment Entry |

## Webhook Flow (e.g., Stripe)

1. Customer submits card details on the payment page
2. Stripe processes the payment
3. Stripe sends a webhook to ERPNext's `/api/method/payments.payment_gateways.doctype.stripe_settings.stripe_settings.webhook` endpoint
4. ERPNext creates/updates Integration Request log
5. Payment Request status updated to "Paid"
6. Payment Entry auto-created and submitted
7. Sales Invoice outstanding amount reduced

## Key Fields on Payment Request

| Field | Purpose |
|---|---|
| `payment_request_type` | "Inward" (customer pays you) vs "Outward" (you pay vendor) |
| `party_type` / `party` | Who pays — Customer, Supplier, etc. |
| `reference_doctype` / `reference_name` | The invoice/document being paid |
| `grand_total` | Amount to collect |
| `payment_url` | Public URL for the payment page (generated on submit) |
| `status` | Current state in the lifecycle |
| `mute_email` | If checked, don't auto-email the payment link |

## Reconciliation

After payment:
1. Go to **Payment Reconciliation** (search in awesome bar)
2. Select the Customer
3. Unpaid invoices and unallocated Payment Entries appear
4. Match them and allocate
5. Submit → accounting entries posted

If the Payment Entry amount exactly matches the invoice outstanding, ERPNext may auto-reconcile.

## Portal Integration

The ERPNext customer portal (`/invoices` route) shows invoices linked to the logged-in customer. Each invoice can display a "Pay Now" button if a Payment Request exists for it. The portal uses the standard ERPNext web templates — customize by overriding in your custom app's `www/` directory.

## Security Notes

- Payment URLs are **public** — anyone with the link can attempt to pay. They are unguessable (long random strings).
- Never expose Payment Gateway API keys in client-side code.
- Use test/sandbox keys during development.
- Webhook endpoints should verify signatures (ERPNext does this automatically for supported gateways).
