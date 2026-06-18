# ERPNext Stock Receipt UI Reference

Use this when a Frappe/ERPNext chat UI needs to list Items and let the user add stock quantity.

## Data model notes

- `Item` is the master record; it does **not** hold current stock quantity.
- Current stock is read from `Bin` (`actual_qty`) and/or Stock Ledger Entry.
- Selectable warehouses should come from `Warehouse` where `is_group = 0`.
- A stock receipt is posted through `Stock Entry`, not by editing `Item`.

## Verified Stock Entry shape

For a simple Material Receipt:

```json
{
  "doctype": "Stock Entry",
  "stock_entry_type": "Material Receipt",
  "company": "<company>",
  "posting_date": "<YYYY-MM-DD>",
  "posting_time": "<HH:MM:SS>",
  "set_posting_time": 1,
  "remarks": "<optional reason>",
  "items": [
    {
      "doctype": "Stock Entry Detail",
      "item_code": "<Item.item_code>",
      "item_name": "<Item.item_name>",
      "qty": "<positive quantity>",
      "uom": "<Item.stock_uom>",
      "stock_uom": "<Item.stock_uom>",
      "conversion_factor": 1,
      "t_warehouse": "<non-group Warehouse>",
      "valuation_rate": null
    }
  ]
}
```

## UI payload to Hermes

Recommended form payload:

```json
{
  "action": "create_stock_entry",
  "stock_entry_type": "Material Receipt",
  "company": "<company>",
  "posting_date": "<YYYY-MM-DD>",
  "posting_time": "<HH:MM:SS>",
  "set_posting_time": 1,
  "item_code": "<Item.item_code>",
  "item_name": "<Item.item_name>",
  "target_warehouse": "<non-group Warehouse>",
  "qty": 1,
  "uom": "<Item.stock_uom>",
  "stock_uom": "<Item.stock_uom>",
  "valuation_rate": null,
  "remarks": "<optional>",
  "current_stock_at_warehouse": 0,
  "post_stock_entry": false
}
```

## Safety defaults

- Default to **creating a draft** Stock Entry unless the user explicitly asks to post immediately.
- If valuation rate is left blank, let ERPNext calculate it when possible.
- If the item/warehouse has no `Bin` row, display current stock as `0` but note that no Bin record exists.
- For batch/serial-managed items, pause and ask for batch/serial details before creating the Stock Entry.
