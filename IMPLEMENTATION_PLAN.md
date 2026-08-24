# PipeERP Desktop-to-Web Parity Implementation Plan

Date: 2026-08-24  
Desktop reference: `origin/main` at `70850aa`  
Web target: `web-rebuild`  
Audit sources: `/home/youssef/Music/AUDIT_DESKTOP_VS_WEB_PARITY.md` and `/home/youssef/Music/ERP_Audit_MFG_AVAILABILITY_WIZARD_ADDED.md`

## Governing decisions

- Desktop is the business source of truth. Web-only business actions are removed or made unreachable from both UI and public API.
- Existing reversal workflows are retained. This includes sales, purchasing, payments, returns/refunds, inventory and treasury reversals where already implemented, subject to their existing integrity guards.
- The enhanced Web dashboard is an owner-approved UI exception: keep daily KPIs, operating activity, attention alerts and permission-aware quick actions.
- Technical protections required by a concurrent Web system (CSRF, idempotency, optimistic locking, audit log, session revocation and normalized UOM storage) remain because they do not add a business decision.
- Existing records created by old Web-only workflows are preserved for audit/history. Removing a workflow must not delete or rewrite historical accounting or inventory records.
- No framework/module rewrite. Changes stay inside the current FastAPI/React architecture.

## Finding-by-finding implementation map

Each row records Desktop behavior, the current Web state after commit `2c5389a`, the required action, likely files, risk, and verification evidence.

### Identity, partners, products, reports and settings

| ID | Module | Desktop behavior | Current Web behavior | Required change | Files affected | Risk | Testing approach |
|---|---|---|---|---|---|---|---|
| ID-1 | Identity/docs | RBAC is live with 17 permissions | Some legacy docs described it as future work | Correct stale wording; no business-code change | `README.md`, parity docs | Low | Documentation grep and link check |
| ID-2 | Identity | A user may have zero permissions | Create/update requires at least one role | Allow an empty role set and expose “بدون صلاحيات” in the user form | identity schemas/service/tests; `SettingsPage.tsx` | Medium | Create zero-role user; login; verify no module access |
| ID-3 | Identity | No forced password-change gate | New user can be forced to `/change-password` | Stop enabling the gate for normal admin-created users; keep password-change page as voluntary/security utility | identity schemas/service; `ProtectedRoute.tsx`; settings/tests | Medium | Create user, first login lands on dashboard; password change still works |
| ID-4 | Identity/bootstrap | First-run is interactive or environment-driven | Web bootstrap is operator CLI | Keep CLI as Web deployment necessity and document the equivalent first-run operation | `web/README.md`, docs | Low | Fresh DB bootstrap and first login |
| ID-5 | Identity/RBAC | Per-user effective permissions | Role-to-permission effective model | Keep; effective behavior is equivalent | identity service/tests | Low | Role matrix navigation/API denial tests |
| ID-6 | Identity/audit | No identity audit table | Web has audit logging | Keep as non-workflow infrastructure | audit/identity tests | Low | Verify audit row after user edit |
| ID-7 | Identity/sessions | No persistent sessions | Privilege edits revoke sessions | Keep as Web security infrastructure | identity service/tests | Low | Update role and verify old session rejection |
| PTR-1 | Partners | Customer and supplier are separate records | Backend permits one dual-role record; normal UI is already split | Enforce exactly one partner type for new/edited records; preserve historical dual-role rows until a separately approved data split | master-data schemas/service/tests; partners UI | High | Reject dual-role payload; customer/supplier screens remain separate; audit existing dual-role count |
| PTR-2 | Partners | Code/name/phone/address only | Backend stores optional tax number; current normal form should not add a Desktop-unseen decision | Remove tax-number input from normal partner workflow while preserving stored legacy data | `PartnersPage.tsx`, tests | Low | Add/edit customer and supplier with Desktop fields only |
| PTR-3 | Accounts | Auditable partner opening balance and reversal | Equivalent ledger and reversal | Keep; reversal is approved | treasury tests | Medium | Post/reverse opening balance and reconcile partner balance |
| PTR-4 | Partners | Partner screen contains linked transactions | Web relocated history to Accounts | Restore read-only linked movements on the customer/supplier detail without duplicating posting actions | partner/treasury read API; `PartnersPage.tsx` | Medium | Select partner and compare movement list with Desktop/account statement |
| PTR-5 | Partners | Soft deactivation | Soft activation toggle | Keep | master-data tests | Low | Deactivate/reactivate and verify selectors |
| PROD-1 | Products | No product-category workflow | Category backend exists; category/track-lot controls are already hidden in normal UI | Keep legacy schema for compatibility; do not expose category CRUD or category decision in normal Web workflow | products/master-data routes and docs | Low | Product form contains only Desktop fields |
| PROD-2 | Products/UOM | Free-text unit | Normalized UOM master | Keep normalized storage as technical consolidation; seed Desktop-equivalent units and show one UOM choice | master-data tests/UI | Low | kg scenario stores `1037.5` as quantity with kg UOM |
| PROD-3 | Products | `track_lots` always true in UI | Backend supports false; UI now sends true | Enforce true in normal product create/update path; retain column internally | master-data service/tests | Low | Create/edit product and verify true |
| RPT-1 | Printing | A4 and 80mm thermal printing | A4 browser printing only | Add an 80mm print layout/action using existing invoice data; do not change posting workflow | reports UI/styles/tests | Medium | Browser print preview at 80mm; posted-only guard |
| RPT-2 | Printing | Fixed 300-DPI A4 renderer | Browser print renderer | Keep browser technology; verify identical fields, pagination and RTL; physical printer remains acceptance evidence | reports UI/styles/docs | Medium | PDF/print snapshot plus physical-printer checklist |
| RPT-3 | Reports | Six reports and RTL XLSX | Same six plus statement export | Keep six report workflows; statement export may remain as output of Desktop statement screen, not a new posting action | reports tests | Low | Generate each XLSX and validate headers/data |
| RPT-4 | Reports | Exactly six report types | Same six | Keep | reports tests | Low | Parameterized six-report test |
| RPT-5 | Settings | Appearance, watermark, multi-phone | Owner requested the selected logo fixed beside the user name instead of a page watermark | **Owner-approved UI exception**: migrate the saved watermark image to a fixed header logo and retain appearance/multi-phone settings | `AppShell.tsx`, `SettingsPage.tsx`, styles | Low | Persist/reload legacy image; verify fixed header position while scrolling |
| RPT-6 | Backup | In-app local DB restore | Safe server-side restore tooling | Keep operational difference; Web cannot replace a live multi-user DB from a browser request safely | system settings/docs/ops tests | High | Create valid backup; restore into isolated DB only |
| RPT-7 | Dashboard | Inventory KPIs only | Enhanced Web dashboard | **Owner-approved exception**: retain daily KPIs, operating activity, attention alerts and permission-aware quick actions | dashboard API/UI/tests | Low | Verify all four sections render and API remains permission-aware |

### Inventory and manufacturing

| ID | Module | Desktop behavior | Current Web behavior | Required change | Files affected | Risk | Testing approach |
|---|---|---|---|---|---|---|---|
| INV-1 | Warehouses | Exactly one `MAIN/المصنع`; creation forbidden | UI shows one, but API still permits more | Enforce single warehouse server-side; allow read/update of the existing factory only; report legacy extra warehouses without deleting them | master-data service/routes/tests | High | Second create rejected; default cannot move; legacy data remains readable |
| INV-2 | Inventory transfer | No inter-warehouse transfer | UI hidden, public POST route still active | Remove/disable new transfer posting from public API; retain reversal/read internals only for historical transactions | inventory routes/schemas/tests/docs | High | POST transfer rejected; existing reversal integrity test still passes |
| INV-3 | Opening stock | Positive stock adjustment | Same mechanism; stale display label may remain | Remove dead `opening_balance` inventory label only | `InventoryPage.tsx` | Low | Stock-card label mapping test |
| INV-4 | Negative stock | FIFO hard block | Equivalent hard block | Keep and regression-test | FIFO/inventory tests | High | Exact insufficient quantity/weight scenarios |
| INV-5 | FIFO dimensions | Quantity core plus Desktop-native weight subsystem | Unified dual-dimension layers | Keep as technical consolidation; golden-value tests must prove equivalent outputs | inventory/sales tests | High | Multi-layer piece and weight FIFO calculations |
| INV-6 | Adjustment reason | Empty notes allowed | Server requires 3 characters | Allow an empty reason, preserving optional notes | inventory schemas/UI/tests | Low | Post positive/negative adjustment with blank notes |
| INV-7 | Reversal | No generic reversal | Web reversal exists | Keep due approved reversal exception; keep audit/idempotency guards | inventory service/routes/tests/docs | High | Reverse untouched movement; reject unsafe reversal |
| INV-8 | Stock card | One row per movement | Allocation-level detail may create multiple rows | Present Desktop movement-level rows and columns; preserve allocation detail internally | inventory service/UI/tests | Medium | One posted movement produces one card row with matching totals |
| MFG-1 | Manufacturing stages | Draft → optional replan → start → complete/cancel | Same | Keep | manufacturing tests | High | State-transition matrix |
| MFG-2 | Material issue | Full planned batches, not incremental runs | Same | Keep | manufacturing tests | High | One start issues full plan once |
| MFG-3 | Completion top-up | Additional batches issued before completion | Same | Keep | manufacturing tests | High | Complete above issued batches and reconcile cost |
| MFG-4 | Mix adjustment | Desktop formulas | Same formulas | Keep with golden values | completion domain tests | High | Formula fixtures copied from Desktop examples |
| MFG-5 | Scrap/output costing | Desktop allocation and remainder formulas | Same | Keep | completion tests | High | Total cost conservation/rounding |
| MFG-6 | Scrap product | Auto-create `SCRAP-{code}` | Same | Keep | manufacturing tests | Medium | Recipe creates/reuses exact scrap product |
| MFG-7 | Scrap replan | Replan from available scrap | Same backend; Web confirmation is simpler | Availability screen will combine replan summary and material table as Desktop does | manufacturing API/UI/tests | High | Low-scrap replan preview and applied batch count |
| MFG-8 | Cancel in-progress | Return issued material | Same | Keep; this is a Desktop-original cancellation and also compatible with reversal policy | manufacturing/inventory tests | High | Cancel restores stock/cost and status |
| MFG-9 | Warehouse binding | Implicit single factory | UI filters to `MAIN`, backend accepts arbitrary warehouse ID | Server resolves/enforces the factory warehouse; no user decision | manufacturing schemas/service/tests/UI | High | Non-MAIN payload rejected; normal create uses MAIN |
| MFG-AVAIL-01 | Manufacturing start | Before issue, show required/available/shortage; basic-material shortage blocks, scrap shortage does not | Web only fails during issue | Add read-only availability preview endpoint and modal before start; backend start independently rechecks the same shortages atomically | manufacturing schemas/service/routes/tests; `ManufacturingPage.tsx`; styles | Critical | Preview values, blocking/optional shortage cases, race-condition recheck, successful issue impact |

### Purchasing and purchase returns

| ID | Module | Desktop behavior | Current Web behavior | Required change | Files affected | Risk | Testing approach |
|---|---|---|---|---|---|---|---|
| PUR-1 | Purchasing | Draft receives directly | Current normal Web button performs approval internally then receipt in one action | Keep one visible receive action; remove standalone approval route from normal/public workflow while retaining old status compatibility | purchasing routes/service/UI/tests | High | Action count: save draft → receive; no approval control |
| PUR-2 | Purchasing invoice | Receipt atomically posts supplier invoice | Fixed in current Web `/receive` flow | Verify transaction rollback guarantees stock and payable are inseparable; backfill audit for old received/uninvoiced orders | purchasing service/migration/tests | Critical | Forced invoice failure rolls back receipt; normal receipt creates invoice |
| PUR-3 | PO statuses | Draft/received | Extra approved/partial/cancel states exist in schema/history | Normal workflow exposes only draft/received; keep legacy statuses readable for old rows and reversals | purchasing serializers/UI/docs | Medium | Fresh order never stops in extra state |
| PUR-4 | Partial receipts | All-at-once receipt | Legacy partial-receipt endpoint remains | Disable new partial receipts from public UI/API; preserve existing receipt records and reversal | purchasing routes/service/tests | High | Partial endpoint rejected; full receive posts all remaining lines |
| PUR-5 | Receipt/invoice reversal | No reversal | Web reversal exists | Keep by explicit exception; retain ordering guard | purchasing tests/docs | High | Invoice must reverse before receipt; inventory/payable restore |
| PUR-6 | Idempotency | Not needed on Desktop | Required by Web | Keep technical retry protection | purchasing tests | Medium | Same key/same body idempotent; changed body rejected |
| PUR-7 | Purchase quantity basis | One quantity carrying its UOM | API/model still requires `cost_basis` and parallel weight columns; UI hardcodes quantity | Remove basis from purchase request/response and logic; use quantity only. Preserve legacy DB columns with fixed `quantity` values for migration safety | purchasing schemas/service/models/migration/tests; `PurchasesPage.tsx` | High | `1037.5 kg` stays quantity 1037.5; loss/cost/payable golden tests |
| PRET-1 | Return prerequisite | Available immediately after receive-created invoice | Fixed if `/receive` succeeds atomically | Verify purchase return is available immediately after receive | purchasing/returns integration tests | High | Two-step PO workflow followed by return |
| PRET-2 | Return reversal | None | Web reversal | Keep by exception | returns/inventory tests/docs | High | Reverse only when no refund; restore stock |
| PRET-3 | Refund reversal | None | Web reversal | Keep by exception | returns/treasury tests/docs | High | Reverse refund and reconcile account |
| PRET-4 | Returnable quantity | Ordered/received quantity minus returns | Web sums receipt lines | With full receipt workflow, verify the sum equals received quantity; retain legacy multi-receipt compatibility | returns tests | High | Full and legacy partial receipt return limits |
| PRET-5 | Return UI | Generic invoice tab and separate refund accounts page | Web embeds sales/purchase sub-tabs | Keep the same user actions inside Accounts; no new business decision. Align labels/order where practical | returns/accounts UI tests | Low | Create return/refund from invoice with same fields |

### Sales and sales returns

| ID | Module | Desktop behavior | Current Web behavior | Required change | Files affected | Risk | Testing approach |
|---|---|---|---|---|---|---|---|
| SAL-1 | Sales status | Draft/delivered | Schema retains cancelled/reversed; normal UI hides actions | Keep reversed for approved exception; stop creating cancelled status; show historical values read-only | sales routes/service/UI/tests | Medium | Fresh flows produce only draft/delivered/reversed |
| SAL-2 | Draft cancellation | No cancellation | Backend route still active, UI hidden | Disable new draft-cancellation endpoint; preserve historical cancelled orders | sales route/tests/docs | Medium | Cancellation request rejected; draft can still deliver |
| SAL-3 | Delivery/invoice reversal | No undo | Backend exists; UI was hidden during prior parity pass | Keep and restore a clearly labelled reversal control with existing payment/inventory integrity guards; document intentional difference | sales UI/service/tests/docs | High | Reverse unpaid delivery; paid invoice blocks; all three statuses/stock reconcile |
| SAL-4 | Piece invoice timing | Automatic on invoice-list refresh | Web creates atomically on delivery | Keep atomic creation because the user action/result is identical and safer | sales tests/docs | Medium | One delivery guarantees posted invoice |
| SAL-5 | Weight invoice timing | Inline on delivery | Same | Keep | sales tests | High | Weight delivery creates invoice in same transaction |
| SAL-6 | Negative stock | FIFO block | Equivalent | Keep | sales/inventory tests | High | Piece and weight insufficient-stock cases |
| SAL-7 | Weight sale | Live weight-card workflow | Same workflow consolidated in Sales | Keep | sales UI/API tests | High | Card weights, vehicle, pricing and invoice |
| SAL-8 | FIFO costing | Oldest eligible layers | Same through unified inventory | Keep; golden tests | sales/inventory tests | High | Multi-layer allocation order/cost |
| SAL-9 | Advance account | Desktop may fall back to default account; live screen centralizes payments | Current normal sales form sends zero advance | Keep advances out of order-entry UI; payments occur in Accounts | sales UI/tests | Medium | Sales form has no payment inputs; Accounts links payment correctly |
| SAL-10 | Concurrency | Single writer | Version/idempotency | Keep technical safety | sales tests | Medium | Stale version and duplicate submit tests |
| SAL-11 | Quotations | Create-only draft quotation | Same | Keep | sales tests | Low | Create/list without invented transitions |
| SAL-12 | Duplicate product | Not allowed | DB uniqueness | Keep | sales tests | Low | Duplicate line rejected |
| SRET-1 | Sales return reversal | None | Web reversal | Keep by exception | returns tests/docs | High | Untouched return reverses; consumed return stock blocks |
| SRET-2 | Refund reversal | None | Web reversal | Keep by exception | returns/treasury tests/docs | High | Refund reversal restores account balance |
| SRET-3 | Returned-stock cost | Desktop averages historical outbound cost for product/order | Web uses exact delivery-line cost | Inventory valuation would change if altered; implement Desktop formula only after explicit valuation approval, otherwise document as remaining difference | returns service/tests/docs | Critical | Multi-layer sale then partial return; compare both formulas and total valuation |
| SRET-4 | Retry/concurrency | None | Idempotency/version locks | Keep technical safety | returns tests | Medium | Duplicate/stale requests |
| SRET-5 | Permissions | Status and permission gated | `returns.manage` + CSRF | Keep | returns/identity tests | Medium | Read-only user denied mutation |

### CRM and treasury/accounting

| ID | Module | Desktop behavior | Current Web behavior | Required change | Files affected | Risk | Testing approach |
|---|---|---|---|---|---|---|---|
| CRM-1 | CRM scheduling | Shipped `AdminOnlyCRMPage`; only admin schedules | Any `crm.manage` holder can schedule | Enforce admin-only scheduling server-side and hide control for non-admin managers | CRM service/routes/UI/tests | Medium | Manager can edit lead but cannot schedule; admin can |
| CRM-2 | CRM customer sync | Customer→lead sync runs at construction/navigation | No equivalent sync | Add idempotent customer-to-lead synchronization when CRM data loads/opens | CRM service/routes/tests | Medium | Existing/new customers create one lead each; repeat is idempotent |
| CRM-3 | CRM reminders | Global 60-second bell + popup | Global bell was added in current shell | Verify count refresh, navigation and permissions | `AppShell.tsx`, CRM API/tests | Low | Badge counts and click-to-CRM |
| CRM-4 | CRM loop | Leads, activities, pipeline, reports | Equivalent | Keep | CRM tests | Medium | End-to-end lead→activity→customer |
| CRM-5 | CRM analytics | Desktop aggregations | Equivalent | Keep | CRM tests | Low | Golden aggregate values |
| TRE-01 | Payment reversal | Delete live row + shadow reversal display | Soft-status reversal | Keep Web model by approved reversal exception; document raw-data difference and verify reports exclude reversed rows | treasury/reports tests/docs | High | Reverse payment; balances/reports/history reconcile |
| TRE-02 | Account transfer reversal | Opposite forward transfer only | Web reversal exists | Keep by exception; retain negative-balance guard | treasury tests/docs | High | Post/reverse transfer and block unsafe reversal |
| TRE-03 | Financial adjustment reversal | No undo | Web reversal exists | Keep by exception | treasury tests/docs | High | Adjustment reversal restores exact balance |
| TRE-04 | Supplier multi-invoice allocation | Only customer receipts split across invoices | Web allows both sides | Restrict allocation mode to customer receipts; supplier payments use Desktop order/advance path | treasury schemas/service/UI/tests | High | Supplier allocation payload rejected; customer allocation still works |
| TRE-05 | Customer account adjustment | No standalone adjustment | Web UI/API creates one | Disable new standalone customer adjustments in UI/API; retain historical rows in balance/history and keep reversal for them | treasury routes/UI/service/tests | Critical | New POST rejected; old row still affects balance and can reverse |
| TRE-06 | Supplier statement | Customer statement only | Unified partner statement | Remove supplier-statement action from normal UI/API; preserve internal read compatibility for old exports if needed | treasury routes/UI/tests | Medium | Customer statement works; supplier option absent/rejected |
| TRE-07 | Idempotency | Not applicable | Required | Keep | treasury tests | Medium | Exact retry tests |
| TRE-08 | Payment/account compatibility | Enforced | Equivalent enum mapping | Keep | treasury/returns tests | High | Cash/bank/cheque/wallet compatibility matrix |
| TRE-09 | Order-entry payment | Centralized in Accounts | Purchase/sales UI now sends zero advances; backend still accepts them | Remove advance fields from order request schemas/public contract; keep historical advance application logic | purchasing/sales schemas/service/tests; Accounts UI | High | Order payload cannot post advance; Accounts payment links to order/invoice |

## Execution phases

1. **Critical:** server-side single warehouse/no transfer; purchasing atomic receive proof/backfill; remove standalone customer adjustments; preserve all reversals.
2. **High:** manufacturing availability endpoint/modal plus atomic recheck; purchase single-quantity contract; remove approval/partial public workflows; restore sales reversal UI; supplier allocation restriction.
3. **Manufacturing:** verify replan/start/completion/cancellation calculations and stock/accounting impact.
4. **Purchasing:** full kg/loss/cost/payable golden flow and purchase return.
5. **Inventory:** movement-level stock card, optional adjustment notes, single-factory enforcement and FIFO regression suite.
6. **Medium/low:** identity gates, CRM sync/admin scheduling, partner linked history, thermal printing, dashboard and documentation alignment.

After every phase, run Ruff, Mypy, focused Pytest, frontend lint/tests/build, and browser workflow tests. Record completed rows and exact evidence in `IMPLEMENTATION_CHANGELOG.md`.

## Explicit stop/risk condition

`SRET-3` changes the cost used when stock re-enters inventory and therefore can change future FIFO valuation. Desktop behavior is clear, but the requested rules explicitly reserve valuation-changing fixes for approval. It will be isolated from all other work and recorded as the only approval-dependent implementation item unless tests prove the two formulas produce the same value for all reachable Web histories.

## 2026-08-25 UI acceptance addendum

| ID | Module | Desktop / required behavior | Previous Web behavior | Required change | Files affected | Risk | Testing approach |
|---|---|---|---|---|---|---|---|
| TRE-10 | Customer statement | Accounts provides a short/summary statement and a detailed statement with invoice-line children | Accounts exposed only the movement table, although the report service already supported invoice details | Add a summary/detailed selector to Accounts and render detailed invoice lines under their movements | `TreasuryPage.tsx`, styles | Low | Existing detailed API test; type-check and build |
| UI-01 | Fixed header logo | Owner-approved logo appears immediately to the right of `3A PIPE` at a readable size | Custom image appeared tiny and after the full title | Reorder header elements and enlarge the custom image viewport | `AppShell.tsx`, styles, layout test | Low | Browser visual check and DOM-order test |
| UI-02 | Financial account cards | Labelled edit action remains inside each card | Generic square icon sizing clipped/overflowed “تعديل” | Scope automatic width to this labelled action | styles | Low | Layout review and build |
| UI-03 | Product deletion | Delete action explicitly says “حذف” | Pale icon-only control appeared blank | Add visible label without changing delete confirmation logic | `ProductsPage.tsx`, styles | Low | UI source review and build |
| UI-04 | Purchase quantities | Positive integer and fractional UOM quantities are accepted | Offset HTML step grid rejected valid integer `100` | Align `min` and `step` to six-decimal quantity precision | `PurchasesPage.tsx` | Low | Browser validity rule review, type-check and build |
