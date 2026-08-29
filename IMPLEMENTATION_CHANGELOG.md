# PipeERP Desktop-to-Web Parity — Implementation Changelog

Date: 2026-08-24  
Desktop reference: `origin/main` at `70850aa`  
Web branch: `web-rebuild`

## Status legend

- **Fixed**: Web behavior changed to match Desktop.
- **Verified**: No code change was required; regression evidence confirms parity.
- **Retained**: Technical Web implementation kept because it does not add a business decision.
- **Approved exception**: Owner-approved behavior intentionally kept, including reversal workflows and the enhanced Web dashboard.
- **Approval required**: Not changed because it affects inventory valuation.

## Identity, partners, products, reports, and dashboard

| ID | Original deviation | Fix or decision | Principal files | Verification |
| --- | --- | --- | --- | --- |
| ID-1 | Old documentation described live features as future work | **Fixed** stale README/parity wording | `README.md`, `web/README.md`, `web/docs/DESKTOP_PARITY_AR.md` | Documentation grep/review |
| ID-2 | Web required at least one role | **Fixed**: zero-role user is accepted and “بدون صلاحيات” is available | identity schemas; `SettingsPage.tsx`; identity tests | Zero-role create/login/API access test |
| ID-3 | Web forced first-login password change | **Fixed** for normal admin-created users; voluntary password change remains | identity schemas/service; `ProtectedRoute.tsx`; identity tests | First login reaches normal app; password-change endpoint still covered |
| ID-4 | First-run mechanism differs because Web is deployed server-side | **Retained** operator bootstrap and documented it | `web/README.md` | Existing bootstrap contract/tests |
| ID-5 | Role storage differs from Desktop per-user UI | **Retained** because effective permissions are equivalent | identity service/tests | Permission matrix tests |
| ID-6 | Web audit log has no Desktop equivalent | **Retained** as non-workflow infrastructure | audit/identity implementation | Audit regression suite |
| ID-7 | Web revokes sessions after privilege changes | **Retained** as Web security infrastructure | identity service/tests | Session-revocation tests |
| PTR-1 | Web accepted one partner as customer and supplier | **Fixed**: new/edit payload must select exactly one type; legacy rows remain readable | master-data schemas/tests | Dual-role request rejected |
| PTR-2 | Web exposed tax number not present in normal Desktop form | **Fixed**: removed from the normal form; legacy value is preserved on edit | `PartnersPage.tsx` | Frontend build and form review |
| PTR-3 | Partner opening-balance storage differs | **Verified** accounting result; reversal kept | treasury tests | Post/reverse balance reconciliation |
| PTR-4 | Linked partner movements were only under Accounts | **Fixed**: added read-only movements to partner detail | master-data route; `PartnersPage.tsx` | API permission/path tests and build |
| PTR-5 | No material behavior difference | **Verified** soft deactivation | master-data tests | Deactivate/reactivate tests |
| PROD-1 | Category infrastructure existed in Web | **Fixed at workflow boundary**: no category management or choice in normal product form | product/master-data UI contract | Frontend review/build |
| PROD-2 | Web normalizes UOM while Desktop stores text | **Retained** normalized storage; the user still selects one UOM | master-data implementation | Decimal/UOM purchase tests |
| PROD-3 | API could disable lot tracking | **Fixed**: create/update always stores `track_lots=true` | master-data service/tests | Product create/edit assertions |
| RPT-1 | Web exposed a thermal 80mm print action not wanted by the owner | **Fixed**: removed the thermal action and all thermal print CSS; Web printing is A4 only | `ReportsPage.tsx`, `styles.css`, docs | Source grep and frontend print-component regression test |
| RPT-2 | Browser output was a generic A4 table unlike the branded Desktop documents | **Fixed**: created one shared branded A4 renderer over the exact Desktop background for ordinary invoices, weight/card invoices, quotations, detailed/short customer statements and a statement summary page; added direct printing inside Sales only for posted invoices | `A4PrintDocuments.tsx`, `SalesPage.tsx`, `ReportsPage.tsx`, `styles.css`, reports schemas/service/tests | Browser-generated PDF is one exact A4 page; rendered visual inspection; backend `97 passed, 7 skipped`; frontend `23 passed`; production build passed |
| RPT-3 | Statement export is colocated differently | **Verified/retained** as output only; no posting workflow added | reports/treasury implementation | Six-report tests |
| RPT-4 | No difference | **Verified** exactly six report types | reports tests | Parameterized report suite |
| RPT-5 | Uploaded logo appeared as a watermark in the middle of every page | **Approved exception requested by owner**: reuse the saved image as a fixed header logo beside the user name; remove the page watermark | `AppShell.tsx`, `SettingsPage.tsx`, styles | Legacy-image migration, visual scroll check, frontend suite/build |
| RPT-6 | Browser cannot safely replace a live DB like the single-user Desktop app | **Retained operational difference**: restore remains an isolated operator action | restore tooling/docs | Restore is restricted to isolated target; no live-browser restore |
| RPT-7 | Web dashboard extends the Desktop inventory-only summary | **Approved exception restored by owner request**: daily KPIs, operating activity, attention alerts and permission-aware quick actions are retained | dashboard route/page | API permission contract, frontend section regression test and build |

## Inventory and manufacturing

| ID | Original deviation | Fix or decision | Principal files | Verification |
| --- | --- | --- | --- | --- |
| INV-1 | Public API allowed multiple warehouses | **Fixed**: only `MAIN / المصنع` can exist; second create and update are rejected | master-data service/tests | Server-side rejection tests |
| INV-2 | Hidden UI transfer still had a public POST API | **Fixed**: public creation route removed; old history/reversal internals retained | inventory route/tests | POST route returns 404/405; reversal regression remains |
| INV-3 | Dead opening-stock display terminology could appear | **Fixed/verified** normal adjustment labels only | inventory UI | Frontend build/review |
| INV-4 | No difference | **Verified** hard negative-stock block | inventory tests | Insufficient FIFO tests |
| INV-5 | Web stores quantity and weight together | **Retained** technical consolidation with equivalent FIFO result | inventory/sales services | Piece and weight FIFO suites |
| INV-6 | Web required a three-character adjustment reason | **Fixed**: notes may be empty | inventory schemas/tests | Blank-note adjustment test |
| INV-7 | Generic reversal is absent from Desktop | **Approved exception** retained with guards | inventory service/routes/tests | Safe/unsafe reversal tests |
| INV-8 | Stock card exposed one row per FIFO allocation | **Fixed**: allocations are aggregated into one movement row; lot names and weighted cost are preserved | inventory service/tests | One movement produces one stock-card row |
| MFG-1 | No material difference | **Verified** draft/start/complete/cancel transitions | manufacturing tests | State-transition suite |
| MFG-2 | No material difference | **Verified** full planned issue at start | manufacturing tests | One-start/one-issue assertions |
| MFG-3 | No material difference | **Verified** top-up issue before larger completion | manufacturing tests | Completion/top-up suite |
| MFG-4 | Formula parity required proof | **Verified** mix-adjustment formulas | manufacturing/domain tests | Golden calculation fixtures |
| MFG-5 | Formula parity required proof | **Verified** scrap/output cost conservation | manufacturing tests | Cost/rounding invariants |
| MFG-6 | No material difference | **Verified** `SCRAP-{code}` creation/reuse | manufacturing tests | Scrap-product assertions |
| MFG-7 | Web replan confirmation lacked Desktop availability context | **Fixed**: replan result is shown inside the new availability workflow | manufacturing service/page | Scrap-shortage/replan tests |
| MFG-8 | Cancellation exists in both products | **Verified** issued material returns on cancel | manufacturing/inventory tests | Stock and status reconciliation |
| MFG-9 | Backend accepted arbitrary warehouse IDs | **Fixed**: create/update enforce the factory warehouse | manufacturing service/tests | Non-factory payload rejection |
| MFG-AVAIL-01 | Web only failed after attempting material issue | **Fixed**: preview shows required, available, issue and shortage; basic shortages block and start atomically rechecks | manufacturing schemas/service/route/page/styles/tests | Preview values, shortage block, no partial issue, success path |

## Purchasing and purchase returns

| ID | Original deviation | Fix or decision | Principal files | Verification |
| --- | --- | --- | --- | --- |
| PUR-1 | Web exposed standalone approval | **Fixed**: normal/public flow is save draft then receive | purchasing route/service/page/tests | Approval route disabled; receive succeeds from draft |
| PUR-2 | Legacy received orders could lack supplier invoices | **Fixed**: atomic receive is canonical and migration backfills legacy gaps | purchasing service; migration `0016`; tests | Receipt/invoice transaction and rollback tests; repeat-safe SQLite migration smoke test and migration-head check |
| PUR-3 | Extra statuses existed in active workflow | **Fixed at boundary**: fresh UI flow exposes draft/received only; legacy statuses remain readable | purchasing route/page/docs | Fresh order transition tests |
| PUR-4 | Public partial receipts remained available | **Fixed**: public partial-receipt POST removed; history and reversal retained | purchasing route/tests | Partial endpoint rejected; full receipt verified |
| PUR-5 | Purchase reversal is not in Desktop | **Approved exception** retained; invoice reverses before receipt | purchasing/treasury tests | Ordering and balance/stock restoration tests |
| PUR-6 | Web idempotency has no Desktop equivalent | **Retained** as retry protection | purchasing service/tests | Same/different request-key tests |
| PUR-7 | Purchase requested quantity/weight basis plus parallel amounts | **Fixed**: public request/response and UI use one `ordered_quantity` carrying its UOM; internal legacy columns stay fixed to quantity | purchasing schemas/service/page/tests; demo seed | `1037.5 kg` quantity and cost/loss golden tests; old fields forbidden |
| PRET-1 | Return availability depended on invoice timing | **Fixed/verified** by atomic receipt+invoice | purchasing/returns tests | Return available immediately after receive |
| PRET-2 | Purchase-return reversal is Web-only | **Approved exception** retained | returns tests | Safe reversal/stock restoration |
| PRET-3 | Refund reversal is Web-only | **Approved exception** retained | returns/treasury tests | Account reconciliation |
| PRET-4 | Web can read historical multi-receipt rows | **Retained** compatibility; new receipts are full and return limits use received quantity | returns tests | Full and legacy limits |
| PRET-5 | Placement differs but user action is equivalent | **Verified/retained** inside Accounts with no extra posting decision | returns/accounts UI | Workflow tests/build |

## Sales, returns, CRM, and treasury

| ID | Original deviation | Fix or decision | Principal files | Verification |
| --- | --- | --- | --- | --- |
| SAL-1 | Fresh Web orders could be cancelled | **Fixed**: new flow produces draft/delivered/reversed; old cancelled rows remain readable | sales route/page/tests | Status transition tests |
| SAL-2 | Draft cancellation backend route was active | **Fixed**: public route removed | sales route/tests | Cancellation request rejected |
| SAL-3 | Reversal backend existed but UI control was hidden | **Approved exception**: restored labelled reversal control with existing guards | `SalesPage.tsx`; sales tests | Unpaid reversal succeeds; blocked dependencies remain blocked |
| SAL-4 | Piece invoice is created atomically instead of during a later list refresh | **Retained** because action/result match and no user step changes | sales service/tests | Delivery guarantees one invoice |
| SAL-5 | No difference | **Verified** weight delivery and invoice are atomic | sales tests | Weight-sale suite |
| SAL-6 | No difference | **Verified** negative-stock block | sales/inventory tests | Quantity and weight shortages |
| SAL-7 | No difference | **Verified** weight-card workflow | sales UI/API tests | Card totals/delivery/invoice |
| SAL-8 | No difference | **Verified** oldest eligible FIFO layers | sales/inventory tests | Multi-layer order/cost |
| SAL-9 | Order API accepted advance fields | **Fixed**: advances removed from sales order contract/UI; payments stay in Accounts | sales schemas/service/page/tests | Old fields forbidden; linked payment tests |
| SAL-10 | Desktop does not need concurrency controls | **Retained** Web version/idempotency protection | sales tests | Stale/duplicate request tests |
| SAL-11 | No difference | **Verified** create-only quotations | sales tests | Create/list tests |
| SAL-12 | No difference | **Verified** duplicate product line is rejected | sales tests | Constraint test |
| SRET-1 | Return reversal is Web-only | **Approved exception** retained | returns tests | Safe/consumed-stock guards |
| SRET-2 | Refund reversal is Web-only | **Approved exception** retained | returns/treasury tests | Balance restoration |
| SRET-3 | Desktop uses historical average outbound cost; Web uses exact delivery-line cost | **Approval required**: deliberately unchanged because changing it alters inventory valuation and later FIFO | returns service/tests/docs | Difference documented; valuation decision isolated |
| SRET-4 | Desktop lacks retry/concurrency controls | **Retained** as Web integrity protection | returns tests | Duplicate/stale request tests |
| SRET-5 | No material difference | **Verified** permissions/status guards | returns/identity tests | Read-only mutation denial |
| CRM-1 | Any `crm.manage` user could schedule | **Fixed**: scheduling is limited to `system_admin` in API and UI | CRM service/route/page/tests | Manager denied; admin allowed |
| CRM-2 | Customers were not synchronized into CRM | **Fixed**: idempotent, row-locked sync runs when CRM options load | CRM service/route/page/tests | Existing/new customer creates one lead; repeat does not duplicate |
| CRM-3 | Reminder behavior needed confirmation | **Verified** global count/navigation remains | CRM/AppShell implementation | CRM/API regression tests |
| CRM-4 | No material difference | **Verified** lead/activity/pipeline/customer loop | CRM tests | End-to-end CRM suite |
| CRM-5 | No material difference | **Verified** aggregate reports | CRM tests | Golden aggregate assertions |
| TRE-01 | Payment reversal storage differs | **Approved exception** retained; reports exclude reversed rows | treasury/reports tests | Balance/history/report reconciliation |
| TRE-02 | Transfer reversal is Web-only | **Approved exception** retained for historical transfers; new inter-account transfer workflow remains outside normal parity UI | treasury tests | Guarded reversal tests |
| TRE-03 | Financial-adjustment reversal is Web-only | **Approved exception** retained | treasury tests | Exact balance restoration |
| TRE-04 | Web let supplier payments allocate across invoices | **Fixed**: only customer receipts allocate; supplier payment links to a purchase order or advance | treasury schemas/page/tests; demo seed | Supplier allocation rejected; customer allocation succeeds |
| TRE-05 | Web created standalone customer account adjustments | **Fixed**: creation removed from UI/public API; old history and its reversal remain | treasury route/page/tests | POST rejected; history/reversal readable |
| TRE-06 | Web exposed supplier statements | **Fixed**: normal API/UI statement is customer-only | treasury route/page/tests | Supplier statement rejected/absent |
| TRE-07 | Desktop lacks idempotency | **Retained** Web retry protection | treasury tests | Exact retry coverage |
| TRE-08 | No material difference | **Verified** payment method/account compatibility | treasury/returns tests | Compatibility matrix |
| TRE-09 | Purchase/sales order contracts accepted advances | **Fixed**: fields removed and forbidden; Accounts remains the payment entry point | purchasing/sales schemas/services/pages/tests | Contract rejection and Accounts payment tests |
| TRE-10 | Desktop Accounts offers summary and detailed customer statements; Accounts Web exposed one undifferentiated statement | **Fixed**: Accounts now offers “مجمل (مختصر)” and “تفصيلي”; detailed mode renders the original invoice lines beneath each invoice movement | `TreasuryPage.tsx`, reports statement service | Existing detailed-statement API test; frontend type-check/build |

## Visual and input corrections

| ID | Original deviation | Fix applied | Verification |
| --- | --- | --- | --- |
| UI-01 | Uploaded company logo was tiny and appeared after the user title | Moved it to the right of `3A PIPE`, enlarged the fixed header slot and compensated for transparent image padding | Browser visual check plus header-order regression test |
| UI-02 | “تعديل” overflowed the fixed 31px cash/bank card action | Gave the labelled card action an automatic width and protected it from wrapping | CSS/layout review and production build |
| UI-03 | Product delete action displayed as an empty pale-red control | Added the explicit `حذف` label while retaining the delete icon and confirmation workflow | Frontend test suite and production build |
| UI-04 | Purchase quantity `100` failed native browser validation because `min=0.000001` and `step=0.001` form an offset step grid | Aligned quantity and purchase-loss precision to six decimal places, so integer and fractional UOM quantities are valid | Type-check/build; native step arithmetic corrected |
| UI-05 | Manufacturing availability wizard used the undefined `--panel` CSS variable, leaving its body transparent over the manufacturing screen | Replaced it with the defined surface color and isolated the header, scrollable material table, result and actions inside an opaque responsive dialog | Frontend suite `21/21`; TypeScript and production build passed |

## Additional deviation found during implementation

| ID | Desktop behavior | Previous Web behavior | Business impact | Action |
| --- | --- | --- | --- | --- |
| ADD-1 | A received purchase always has a payable document | Old Web records created before atomic receive could be `received` without a supplier invoice | Return/payment workflow could be unavailable and payables understated | Added data-only migration `20260824_0016` to create one posted invoice for each affected received order without rewriting stock or deleting history |

## Verification summary

- Backend suite: `97 passed, 7 skipped`.
- Frontend suite: `21 passed`.
- Ruff: passed.
- Mypy: passed.
- ESLint: passed.
- Production frontend build: passed.
- The in-app browser reached and rendered the local login surface with no console errors. Authenticated visual acceptance requires an existing signed-in session or a user-provided login; all authenticated workflows are covered by API/frontend integration tests in this delivery.

## Files changed

- Backend routes/services/schemas in identity, master data, inventory, purchasing, sales, treasury, manufacturing, CRM, and dashboard.
- Frontend pages for dashboard, purchases, sales, treasury, inventory-linked partner history, manufacturing, CRM, reports, users, and routing.
- Backend/API tests for every changed business boundary.
- Demo seeding contract and migration `20260824_0016`.
- `IMPLEMENTATION_PLAN.md`, this changelog, and parity/run documentation.
