# Sprint 1 Acceptance Tests

## Master Data
1. Create a supplier.
2. Create a customer.
3. Create a raw material item with min stock.
4. Create a finished product item.
5. Create or review warehouses.

## Inventory Adjustment
1. Open Inventory.
2. Select an item.
3. Enter a positive quantity.
4. Click the adjustment button.
5. Confirm the Inventory balance changes.
6. Open Dashboard and confirm stock KPIs changed.
7. Open Stock Card and confirm an adjustment movement exists.

## Purchase Flow
1. Open Purchases.
2. Select supplier, raw item, lot, quantity, unit and price.
3. Save draft purchase order.
4. Select it and click Receive.
5. Confirm Inventory increased.
6. Confirm Dashboard changed.
7. Confirm Stock Card contains a purchase movement with supplier and lot.

## Sales Flow
1. Open Sales.
2. Select customer and finished product.
3. Enter quantity and price.
4. Save draft sales order.
5. Select it and click Deliver.
6. Confirm Inventory decreased.
7. Confirm Stock Card contains a sale movement with customer.

## Done Criteria
Sprint 1 is accepted when product master data, partners, warehouses, purchases, sales, inventory, dashboard and stock card work together on the same SQLite database without re-entering data manually.
