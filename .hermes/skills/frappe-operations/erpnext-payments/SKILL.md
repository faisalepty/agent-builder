---
name: erpnext-payments
description: Implement customer-facing payment portals in ERPNext — Payment Requests, gateway configuration, portal setup, and payment reconciliation. Use when the user wants customers to self-serve invoice payments online, set up Stripe/Razorpay/PayPal in ERPNext, configure the customer portal for payments, or automate payment request creation.
metadata:
  hermes:
    tags: [erpnext, payments, portal, stripe, customer-self-service]
    category: frappe-operations
---

# ERPNext Customer Payment Portal

## Scope

Covers **customer-side** payment flows in ERPNext:
- Payment Request creation (manual and automated)
- Payment gateway setup (Stripe, Razorpay, PayPal, etc.)
- Customer portal configuration for self-service payment
- Payment reconciliation after customer pays

Does **not** cover vendor/supplier payments, payroll, or internal accounting.

## Common Ambiguity

When the user says "customer portal," they often mean **payment portal** — a place where customers log in and pay outstanding invoices. Always clarify if they mean general portal (docs from memory: `frappe-workspace` / `frappe-doctype` skills) vs. payment-specific flow (this skill).

## Prerequisites

- ERPNext installed and running
- A payment gateway app installed (Stripe via `payments` app, Razorpay, PayPal — see below)
- Customer records linked to Website User accounts with the **Customer** role
- Sales Invoices in "Submitted" status for the amounts to collect

## Workflow

### 1. Install Payment Gateway

ERPNext core does not bundle gateway logic. Install one or more:

| Gateway | App | Command |
|---|---|---|
| Stripe | `payments` (bundled with ERPNext v14+) | Already included |
| Razorpay | `razorpay_integration` | `bench get-app razorpay_integration` |
| PayPal | `paypal_integration` | `bench get-app paypal_integration` |
| GoCardless | `gocardless_integration` | `bench get-app gocardless_integration` |

After installing, restart the bench and run `bench migrate`.

### 2. Configure Payment Gateway Account

1. Search **Payment Gateway Account** in the Frappe awesome bar
2. Select the gateway (e.g., Stripe)
3. Enter API credentials (publishable key, secret key)
4. Set the payment account (bank account to receive funds)
5. Mark as Default if applicable
6. Save

For Stripe: keys come from Dashboard → Developers → API Keys. Use test keys for sandbox mode.

### 3. Create Payment Requests

**Manual:**
1. Go to **Payment Request** → New
2. **Party Type** = Customer, **Party** = select customer
3. **Reference Doctype** = Sales Invoice, **Reference Name** = invoice
4. **Grand Total** = amount (usually auto-filled from invoice)
5. **Email To** = customer email
6. Save & Submit → ERPNext generates a **Payment URL**

**Automated (script):**

```python
import frappe

def create_payment_request(invoice_name, customer_email=None):
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    pr = frappe.get_doc({
        "doctype": "Payment Request",
        "payment_request_type": "Inward",
        "party_type": "Customer",
        "party": invoice.customer,
        "reference_doctype": "Sales Invoice",
        "reference_name": invoice.name,
        "grand_total": invoice.outstanding_amount,
        "email_to": customer_email or frappe.db.get_value(
            "Contact", {"name": invoice.contact_email}, "email_id"
        ),
    })
    pr.insert(ignore_permissions=True)
    pr.submit()
    return pr.payment_url
```

### 4. Deliver Payment Link to Customer

- **Email**: ERPNext sends automatically on submit (if `email_to` is set) using a template containing `{{ payment_url }}`
- **Portal**: Customer logs in to the portal and sees outstanding invoices with pay buttons
- **Manual**: Copy the Payment URL from the Payment Request and send via any channel

### 5. Customer Pays

The customer opens the payment URL and sees:
- Invoice details (number, date, line items, amount)
- Payment form (Stripe Elements, Razorpay checkout, etc.)
- On success: confirmation + ERPNext auto-creates a **Payment Entry**

### 6. Reconcile

ERPNext auto-creates a submitted Payment Entry on successful payment. Use **Payment Reconciliation** to match it against the Sales Invoice, or it may auto-reconcile if the amounts match exactly.

## Customer Portal Setup (Self-Service)

For a full self-service portal where customers log in and pay multiple invoices:

1. **Portal Settings**: Search in awesome bar → configure default portal
2. **Portal Menu Items**: Ensure "Invoices" is listed (route `/invoices`, Reference DocType = Sales Invoice, Role = Customer)
3. **Customer Users**: Each customer needs a Website User with the Customer role, linked to their Contact/Customer record
4. Payment links appear on invoice views in the portal

## Troubleshooting

- **Payment URL is empty**: The Payment Request must be submitted, not just saved. Check that a Payment Gateway Account is configured and default.
- **Customer sees all invoices, not just theirs**: Verify the user has the Customer role and the Customer field is set on the User record.
- **Payment Entry not created**: Check Integration Request logs for webhook failures. Verify the gateway webhook endpoint is reachable from the internet.
- **Gateway not listed in Payment Gateway Account**: The gateway app isn't installed. Run `bench get-app <app>` and `bench migrate`.

## See Also

- `references/payment-flow.md` — detailed end-to-end flow diagram and status lifecycle
