import {
  Beaker,
  Check,
  Factory,
  PackageCheck,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Scale,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type FormEvent,
  type SetStateAction,
} from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { clientId } from "../lib/clientId";

type Tab = "orders" | "recipes";
type Option = {
  id: string;
  code: string;
  name_ar: string;
  product_type: string;
  standard_weight_kg: string;
};
type Recipe = {
  id: string;
  code: string;
  name_ar: string;
  scrap_product_id: string;
  scrap_product_code: string;
  suggested_scrap_per_batch: string;
  notes: string;
  is_active: boolean;
  version: number;
  outputs: Array<{
    id: string;
    product_id: string;
    product_code: string;
    product_name_ar: string;
    standard_weight_kg: string;
  }>;
  components: Array<{
    id: string;
    product_id: string;
    product_code: string;
    product_name_ar: string;
    quantity_per_batch: string;
    display_order: number;
  }>;
};
type Material = {
  id: string;
  product_id: string;
  product_code: string;
  product_name_ar: string;
  component_kind: "material" | "scrap";
  quantity_per_batch: string;
  planned_quantity: string;
  issued_quantity: string;
  used_quantity: string;
  returned_quantity: string;
  issued_cost: string;
  used_cost: string;
};
type Output = {
  id: string;
  product_id: string;
  product_code: string;
  product_name_ar: string;
  planned_quantity: string;
  standard_weight_kg: string;
  good_quantity: string;
  defective_quantity: string;
  actual_weight_kg: string;
  unit_cost: string;
  line_cost: string;
};
type Order = {
  id: string;
  order_number: string;
  recipe_id: string;
  recipe_code: string;
  recipe_name_ar: string;
  warehouse_id: string;
  warehouse_name_ar: string;
  status: "draft" | "in_progress" | "completed" | "cancelled";
  order_date: string;
  planned_batches: number;
  issued_batches: number;
  actual_batches: number;
  target_weight_kg: string;
  planned_input_weight_kg: string;
  returned_scrap_quantity: string;
  material_cost: string;
  finished_cost: string;
  weight_variance_kg: string;
  notes: string;
  cancellation_reason: string;
  version: number;
  outputs: Output[];
  materials: Material[];
  completion: null | {
    full_batches: number;
    modified_batches: number;
    actual_output_weight_kg: string;
    scrap_weight_kg: string;
    average_input_cost_per_kg: string;
    adjustments: Array<{
      id: string;
      excluded_product_name_ar: string;
      batch_count: number;
      reason: string;
      cost_amount: string;
      actual_material_quantities: Array<{
        product_id: string;
        product_name_ar: string;
        actual_quantity: string;
      }>;
    }>;
  };
};
type Options = {
  recipes: Option[];
  warehouses: Option[];
  output_products: Option[];
  material_products: Option[];
  scrap_products: Option[];
};
type DraftLine = { product_id: string; quantity: string };
type AdjustmentDraft = {
  excluded_product_id: string;
  batch_count: string;
  reason: string;
  quantities: Record<string, string>;
};

const blankOptions: Options = {
  recipes: [],
  warehouses: [],
  output_products: [],
  material_products: [],
  scrap_products: [],
};
const statusLabels: Record<Order["status"], string> = {
  draft: "مسودة",
  in_progress: "جارٍ",
  completed: "مكتمل",
  cancelled: "ملغي",
};
const number = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 3 });
const money = new Intl.NumberFormat("ar-EG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function ManufacturingPage() {
  const { user } = useAuth();
  const canManage = user?.permissions.includes("manufacturing.manage") ?? false;
  const [tab, setTab] = useState<Tab>("orders");
  const [options, setOptions] = useState<Options>(blankOptions);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editingRecipeId, setEditingRecipeId] = useState("");
  const [editingOrderId, setEditingOrderId] = useState("");

  const [recipeForm, setRecipeForm] = useState({
    code: "",
    name_ar: "",
    suggested_scrap_per_batch: "0",
    notes: "",
  });
  const [recipeOutputs, setRecipeOutputs] = useState<string[]>([]);
  const [recipeComponents, setRecipeComponents] = useState<DraftLine[]>([
    { product_id: "", quantity: "" },
  ]);
  const [orderForm, setOrderForm] = useState({
    recipe_id: "",
    warehouse_id: "",
    notes: "",
  });
  const [orderOutputs, setOrderOutputs] = useState<DraftLine[]>([
    { product_id: "", quantity: "" },
  ]);
  const [scrapInputs, setScrapInputs] = useState<DraftLine[]>([]);
  const [completion, setCompletion] = useState({
    actual_batches: "",
    scrap_weight_kg: "0",
    notes: "",
  });
  const [completionOutputs, setCompletionOutputs] = useState<
    Record<string, { good: string; defective: string; weight: string }>
  >({});
  const [adjustments, setAdjustments] = useState<AdjustmentDraft[]>([]);

  const selected = useMemo(
    () => orders.find((item) => item.id === selectedId) ?? orders[0] ?? null,
    [orders, selectedId],
  );
  const activeRecipe = useMemo(
    () => recipes.find((item) => item.id === orderForm.recipe_id),
    [recipes, orderForm.recipe_id],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextOptions, nextRecipes, nextOrders] = await Promise.all([
        api<Options>("/manufacturing/options"),
        api<Recipe[]>("/manufacturing/recipes"),
        api<Order[]>("/manufacturing/orders?limit=250"),
      ]);
      const factoryWarehouse =
        nextOptions.warehouses.find((item) => item.code === "MAIN") ??
        nextOptions.warehouses[0];
      setOptions({
        ...nextOptions,
        warehouses: factoryWarehouse ? [factoryWarehouse] : [],
      });
      setRecipes(nextRecipes);
      setOrders(nextOrders);
      setSelectedId((current) =>
        nextOrders.some((item) => item.id === current)
          ? current
          : (nextOrders[0]?.id ?? ""),
      );
      setOrderForm((current) => ({
        ...current,
        recipe_id: current.recipe_id || nextRecipes[0]?.id || "",
        warehouse_id:
          current.warehouse_id || factoryWarehouse?.id || "",
      }));
      setRecipeComponents((current) =>
        current.map((line, index) => ({
          ...line,
          product_id:
            line.product_id ||
            nextOptions.material_products[index]?.id ||
            nextOptions.material_products[0]?.id ||
            "",
        })),
      );
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "تعذر تحميل شاشة التصنيع",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!activeRecipe) return;
    setOrderOutputs((current) =>
      current.map((line, index) => ({
        ...line,
        product_id:
          activeRecipe.outputs[index]?.product_id ||
          activeRecipe.outputs[0]?.product_id ||
          "",
      })),
    );
  }, [activeRecipe]);
  useEffect(() => {
    if (!selected || selected.status !== "in_progress") return;
    setCompletion({
      actual_batches: String(
        selected.issued_batches || selected.planned_batches,
      ),
      scrap_weight_kg: "0",
      notes: "",
    });
    setCompletionOutputs(
      Object.fromEntries(
        selected.outputs.map((item) => [
          item.product_id,
          { good: item.planned_quantity, defective: "0", weight: "" },
        ]),
      ),
    );
    setAdjustments([]);
  }, [selected]);

  function showError(reason: unknown, fallback: string) {
    setError(reason instanceof ApiError ? reason.message : fallback);
  }
  async function perform(
    action: () => Promise<unknown>,
    success: string,
  ): Promise<boolean> {
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      await load();
      return true;
    } catch (reason) {
      showError(reason, "تعذر إتمام عملية التصنيع");
      return false;
    } finally {
      setSubmitting(false);
    }
  }
  function updateLine(
    setter: Dispatch<SetStateAction<DraftLine[]>>,
    index: number,
    field: keyof DraftLine,
    value: string,
  ) {
    setter((current) =>
      current.map((line, lineIndex) =>
        lineIndex === index ? { ...line, [field]: value } : line,
      ),
    );
  }

  async function saveRecipe(event: FormEvent) {
    event.preventDefault();
    const recipe = recipes.find((item) => item.id === editingRecipeId);
    const saved = await perform(
      () =>
        api(
          editingRecipeId
            ? `/manufacturing/recipes/${editingRecipeId}`
            : "/manufacturing/recipes",
          {
            method: editingRecipeId ? "PUT" : "POST",
            body: JSON.stringify({
              ...recipeForm,
              ...(recipe ? { version: recipe.version } : {}),
              output_product_ids: recipeOutputs,
              components: recipeComponents.map((item) => ({
                product_id: item.product_id,
                quantity_per_batch: item.quantity,
              })),
            }),
          },
        ),
      editingRecipeId
        ? "تم تحديث الخلطة."
        : "تم إنشاء الخلطة ومنتج الكسر الخاص بها.",
    );
    if (saved) resetRecipeForm();
  }
  function resetRecipeForm() {
    setEditingRecipeId("");
    setRecipeForm({
      code: "",
      name_ar: "",
      suggested_scrap_per_batch: "0",
      notes: "",
    });
    setRecipeOutputs([]);
    setRecipeComponents([
      { product_id: options.material_products[0]?.id || "", quantity: "" },
    ]);
  }
  function editRecipe(item: Recipe) {
    setEditingRecipeId(item.id);
    setRecipeForm({
      code: item.code,
      name_ar: item.name_ar,
      suggested_scrap_per_batch: item.suggested_scrap_per_batch,
      notes: item.notes,
    });
    setRecipeOutputs(item.outputs.map((output) => output.product_id));
    setRecipeComponents(
      item.components.map((component) => ({
        product_id: component.product_id,
        quantity: component.quantity_per_batch,
      })),
    );
  }
  async function saveOrder(event: FormEvent) {
    event.preventDefault();
    const order = orders.find((item) => item.id === editingOrderId);
    const saved = await perform(
      () =>
        api(
          editingOrderId
            ? `/manufacturing/orders/${editingOrderId}`
            : "/manufacturing/orders",
          {
            method: editingOrderId ? "PUT" : "POST",
            headers: editingOrderId
              ? undefined
              : {
                  "Idempotency-Key": clientId("manufacturing-create"),
                },
            body: JSON.stringify({
              ...orderForm,
              ...(order ? { version: order.version } : {}),
              outputs: orderOutputs.map((item) => ({
                product_id: item.product_id,
                quantity: item.quantity,
              })),
              scrap_inputs: scrapInputs
                .filter((item) => item.product_id && Number(item.quantity) > 0)
                .map((item) => ({
                  product_id: item.product_id,
                  quantity_per_batch: item.quantity,
                })),
            }),
          },
        ),
      editingOrderId
        ? "تم تحديث مسودة أمر التصنيع."
        : "تم إنشاء أمر التصنيع وحساب الخلطات المطلوبة.",
    );
    if (saved) resetOrderForm();
  }
  function resetOrderForm() {
    setEditingOrderId("");
    setOrderOutputs([
      { product_id: activeRecipe?.outputs[0]?.product_id || "", quantity: "" },
    ]);
    setScrapInputs([]);
    setOrderForm((current) => ({ ...current, notes: "" }));
  }
  function editOrder(item: Order) {
    setEditingOrderId(item.id);
    setOrderForm({
      recipe_id: item.recipe_id,
      warehouse_id: item.warehouse_id,
      notes: item.notes,
    });
    setOrderOutputs(
      item.outputs.map((output) => ({
        product_id: output.product_id,
        quantity: output.planned_quantity,
      })),
    );
    setScrapInputs(
      item.materials
        .filter((material) => material.component_kind === "scrap")
        .map((material) => ({
          product_id: material.product_id,
          quantity: material.quantity_per_batch,
        })),
    );
  }
  async function start(item: Order) {
    await perform(
      () =>
        api(`/manufacturing/orders/${item.id}/start`, {
          method: "POST",
          headers: {
            "Idempotency-Key": clientId("manufacturing-start"),
          },
          body: JSON.stringify({ version: item.version }),
        }),
      "تم صرف الخامات من FIFO وبدء الأمر.",
    );
  }
  async function replan(item: Order) {
    setSubmitting(true);
    setError("");
    try {
      const preview = await api<{
        changed: boolean;
        old_batches: number;
        new_batches: number;
        usable_scrap_kg: string;
      }>(`/manufacturing/orders/${item.id}/replan-preview`);
      if (!preview.changed) {
        setNotice("الخطة الحالية تغطي وزن الهدف وفق الكسر المتاح.");
        return;
      }
      if (
        !window.confirm(
          `الكسر المتاح يغيّر الخطة من ${preview.old_batches} إلى ${preview.new_batches} خلطات. تطبيق الخطة؟`,
        )
      )
        return;
      await api(`/manufacturing/orders/${item.id}/replan`, {
        method: "POST",
        body: JSON.stringify({ version: item.version }),
      });
      setNotice("تم تطبيق إعادة التخطيط حسب الكسر المتاح.");
      await load();
    } catch (reason) {
      showError(reason, "تعذر إعادة التخطيط");
    } finally {
      setSubmitting(false);
    }
  }
  async function removeDraft(item: Order) {
    if (!window.confirm(`حذف المسودة ${item.order_number}؟`)) return;
    await perform(
      () =>
        api(`/manufacturing/orders/${item.id}?version=${item.version}`, {
          method: "DELETE",
        }),
      "تم حذف مسودة أمر التصنيع.",
    );
  }
  async function cancel(item: Order) {
    const reason = window.prompt("اكتب سبب إلغاء أمر التصنيع الجاري")?.trim();
    if (!reason) return;
    await perform(
      () =>
        api(`/manufacturing/orders/${item.id}/cancel`, {
          method: "POST",
          headers: {
            "Idempotency-Key": clientId("manufacturing-cancel"),
          },
          body: JSON.stringify({ version: item.version, reason }),
        }),
      "تم إلغاء الأمر ورد كل الخامات المصروفة.",
    );
  }
  async function complete(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    await perform(
      () =>
        api(`/manufacturing/orders/${selected.id}/complete`, {
          method: "POST",
          headers: {
            "Idempotency-Key": clientId("manufacturing-complete"),
          },
          body: JSON.stringify({
            version: selected.version,
            actual_batches: Number(completion.actual_batches),
            scrap_weight_kg: completion.scrap_weight_kg,
            notes: completion.notes,
            outputs: selected.outputs.map((item) => ({
              product_id: item.product_id,
              good_quantity: completionOutputs[item.product_id]?.good || "0",
              defective_quantity:
                completionOutputs[item.product_id]?.defective || "0",
              actual_weight_kg:
                completionOutputs[item.product_id]?.weight || "0",
            })),
            adjustments: adjustments.map((item) => ({
              excluded_product_id: item.excluded_product_id,
              batch_count: Number(item.batch_count),
              reason: item.reason,
              actual_material_quantities: Object.entries(item.quantities)
                .filter(([, value]) => value !== "")
                .map(([product_id, actual_quantity]) => ({
                  product_id,
                  actual_quantity,
                })),
            })),
          }),
        }),
      "تم إكمال الأمر وإضافة الإنتاج والهالك ورد الخامات غير المستخدمة.",
    );
  }

  return (
    <AppShell>
      <section className="page-heading manufacturing-heading">
        <div>
          <h2>التصنيع</h2>
          <p>عرّف الخلطة مرة واحدة، اجمع مقاسات المواسير المطلوبة، ثم ابدأ الإنتاج بخطوات واضحة.</p>
        </div>
        <button
          className="secondary-button"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw size={17} /> تحديث
        </button>
      </section>
      {error ? (
        <div className="alert alert--error" role="alert">
          <TriangleAlert size={17} />
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="alert alert--success">
          <Check size={17} />
          {notice}
        </div>
      ) : null}
      <div className="sales-tabs manufacturing-tabs">
        <button
          className={tab === "orders" ? "active" : ""}
          onClick={() => setTab("orders")}
        >
          <Factory size={16} /> أوامر التصنيع
        </button>
        <button
          className={tab === "recipes" ? "active" : ""}
          onClick={() => setTab("recipes")}
        >
          <Beaker size={16} /> تعريف الخلطات
        </button>
      </div>

      {tab === "recipes" ? (
        <section className="master-layout manufacturing-layout">
          <article className="panel">
            <header className="panel__head">
              <div>
                <h3>الخلطات المسجلة</h3>
                <p>
                  كل منتج نهائي مرتبط بخلطة نشطة واحدة، والكسر يُنشأ تلقائيًا.
                </p>
              </div>
            </header>
            <div className="manufacturing-recipe-grid">
              {recipes.map((item) => (
                <button
                  type="button"
                  className="manufacturing-recipe-card"
                  key={item.id}
                  onClick={() => canManage && editRecipe(item)}
                >
                  <span>
                    <Beaker size={19} />
                  </span>
                  <div>
                    <strong>{item.name_ar}</strong>
                    <small>
                      {item.code} ·{" "}
                      {item.outputs
                        .map((output) => output.product_name_ar)
                        .join("، ")}
                    </small>
                  </div>
                  <b>
                    {number.format(
                      Number(
                        item.components.reduce(
                          (sum, line) => sum + Number(line.quantity_per_batch),
                          0,
                        ),
                      ),
                    )}{" "}
                    كجم
                  </b>
                  {canManage ? <Pencil size={15} /> : null}
                </button>
              ))}
            </div>
          </article>
          {canManage ? (
            <article className="panel master-form-card">
              <header className="panel__head">
                <div>
                  <h3>{editingRecipeId ? "تعديل الخلطة" : "خلطة جديدة"}</h3>
                  <p>الخامات الأساسية لكل خلطة إنتاج.</p>
                </div>
                {editingRecipeId ? (
                  <button type="button" className="mini-action" onClick={resetRecipeForm}>
                    <X size={16} />
                  </button>
                ) : null}
              </header>
              <form
                className="compact-form manufacturing-form"
                onSubmit={(event) => void saveRecipe(event)}
              >
                <label>
                  كود الخلطة
                  <input
                    required
                    value={recipeForm.code}
                    onChange={(event) =>
                      setRecipeForm({ ...recipeForm, code: event.target.value })
                    }
                  />
                </label>
                <label>
                  اسم الخلطة
                  <input
                    required
                    value={recipeForm.name_ar}
                    onChange={(event) =>
                      setRecipeForm({
                        ...recipeForm,
                        name_ar: event.target.value,
                      })
                    }
                  />
                </label>
                <fieldset>
                  <legend>المنتجات النهائية</legend>
                  <div className="manufacturing-checks">
                    {options.output_products.map((item) => (
                      <label className="check-field" key={item.id}>
                        <input
                          type="checkbox"
                          checked={recipeOutputs.includes(item.id)}
                          onChange={(event) =>
                            setRecipeOutputs((current) =>
                              event.target.checked
                                ? [...current, item.id]
                                : current.filter((id) => id !== item.id),
                            )
                          }
                        />
                        {item.name_ar}{" "}
                        <small>{item.standard_weight_kg} كجم</small>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <fieldset>
                  <legend>الخامات لكل خلطة</legend>
                  {recipeComponents.map((line, index) => (
                    <div className="manufacturing-line" key={index}>
                      <select
                        value={line.product_id}
                        onChange={(event) =>
                          updateLine(
                            setRecipeComponents,
                            index,
                            "product_id",
                            event.target.value,
                          )
                        }
                      >
                        {options.material_products.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.code} — {item.name_ar}
                          </option>
                        ))}
                      </select>
                      <input
                        required
                        inputMode="decimal"
                        placeholder="الكمية كجم"
                        value={line.quantity}
                        onChange={(event) =>
                          updateLine(
                            setRecipeComponents,
                            index,
                            "quantity",
                            event.target.value,
                          )
                        }
                      />
                      {recipeComponents.length > 1 ? (
                        <button
                          type="button"
                          className="mini-action"
                          onClick={() =>
                            setRecipeComponents((current) =>
                              current.filter(
                                (_, lineIndex) => lineIndex !== index,
                              ),
                            )
                          }
                        >
                          <X size={15} />
                        </button>
                      ) : null}
                    </div>
                  ))}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() =>
                      setRecipeComponents((current) => [
                        ...current,
                        {
                          product_id: options.material_products[0]?.id || "",
                          quantity: "",
                        },
                      ])
                    }
                  >
                    <Plus size={15} /> خامة
                  </button>
                </fieldset>
                <label>
                  الكسر المقترح لكل خلطة
                  <input
                    inputMode="decimal"
                    value={recipeForm.suggested_scrap_per_batch}
                    onChange={(event) =>
                      setRecipeForm({
                        ...recipeForm,
                        suggested_scrap_per_batch: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  ملاحظات
                  <textarea
                    value={recipeForm.notes}
                    onChange={(event) =>
                      setRecipeForm({
                        ...recipeForm,
                        notes: event.target.value,
                      })
                    }
                  />
                </label>
                <button
                  className="primary-button"
                  disabled={submitting || recipeOutputs.length === 0}
                >
                  {editingRecipeId ? <Pencil size={16} /> : <Plus size={16} />} {editingRecipeId ? "حفظ التعديلات" : "حفظ الخلطة"}
                </button>
              </form>
            </article>
          ) : null}
        </section>
      ) : (
        <>
          <section className="master-layout manufacturing-layout">
            <article className="panel">
              <header className="panel__head">
                <div>
                  <h3>أوامر التصنيع</h3>
                  <p>المسودات والأوامر الجارية والمكتملة مع التكلفة الفعلية.</p>
                </div>
              </header>
              <div className="manufacturing-order-list">
                {orders.map((item) => (
                  <button
                    type="button"
                    className={`manufacturing-order-card ${selected?.id === item.id ? "manufacturing-order-card--selected" : ""}`}
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <span className="manufacturing-order-card__icon">
                      <Factory size={18} />
                    </span>
                    <span>
                      <strong>
                        {item.order_number} · {item.recipe_name_ar}
                      </strong>
                      <small>
                        {new Date(item.order_date).toLocaleDateString("ar-EG")}{" "}
                        · {item.warehouse_name_ar}
                      </small>
                    </span>
                    <em
                      className={`manufacturing-status manufacturing-status--${item.status}`}
                    >
                      {statusLabels[item.status]}
                    </em>
                    <b>{item.planned_batches} خلطة</b>
                  </button>
                ))}
              </div>
            </article>
            {canManage ? (
              <article className="panel master-form-card">
                <header className="panel__head">
                  <div>
                    <h3>{editingOrderId ? "تعديل مسودة التصنيع" : "أمر تصنيع جديد"}</h3>
                    <p>يُحسب وزن الهدف وعدد الخلطات تلقائيًا.</p>
                  </div>
                  {editingOrderId ? (
                    <button type="button" className="mini-action" onClick={resetOrderForm}>
                      <X size={16} />
                    </button>
                  ) : null}
                </header>
                <form
                  className="compact-form manufacturing-form"
                  onSubmit={(event) => void saveOrder(event)}
                >
                  <label>
                    الخلطة
                    <select
                      required
                      value={orderForm.recipe_id}
                      onChange={(event) =>
                        setOrderForm({
                          ...orderForm,
                          recipe_id: event.target.value,
                        })
                      }
                    >
                      {recipes.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.code} — {item.name_ar}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    المخزن
                    <select
                      required
                      value={orderForm.warehouse_id}
                      onChange={(event) =>
                        setOrderForm({
                          ...orderForm,
                          warehouse_id: event.target.value,
                        })
                      }
                    >
                      {options.warehouses.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name_ar}
                        </option>
                      ))}
                    </select>
                  </label>
                  <fieldset>
                    <legend>الإنتاج المطلوب</legend>
                    {orderOutputs.map((line, index) => (
                      <div className="manufacturing-line" key={index}>
                        <select
                          value={line.product_id}
                          onChange={(event) =>
                            updateLine(
                              setOrderOutputs,
                              index,
                              "product_id",
                              event.target.value,
                            )
                          }
                        >
                          {activeRecipe?.outputs.map((item) => (
                            <option
                              key={item.product_id}
                              value={item.product_id}
                            >
                              {item.product_name_ar}
                            </option>
                          ))}
                        </select>
                        <input
                          required
                          inputMode="decimal"
                          placeholder="العدد المطلوب"
                          value={line.quantity}
                          onChange={(event) =>
                            updateLine(
                              setOrderOutputs,
                              index,
                              "quantity",
                              event.target.value,
                            )
                          }
                        />
                        {orderOutputs.length > 1 ? (
                          <button
                            type="button"
                            className="mini-action"
                            onClick={() =>
                              setOrderOutputs((current) =>
                                current.filter(
                                  (_, lineIndex) => lineIndex !== index,
                                ),
                              )
                            }
                          >
                            <X size={15} />
                          </button>
                        ) : null}
                      </div>
                    ))}
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() =>
                        setOrderOutputs((current) => [
                          ...current,
                          {
                            product_id:
                              activeRecipe?.outputs[0]?.product_id || "",
                            quantity: "",
                          },
                        ])
                      }
                    >
                      <Plus size={15} /> مقاس
                    </button>
                  </fieldset>
                  <fieldset>
                    <legend>كسر معاد استخدامه — اختياري</legend>
                    {scrapInputs.map((line, index) => (
                      <div className="manufacturing-line" key={index}>
                        <select
                          value={line.product_id}
                          onChange={(event) =>
                            updateLine(
                              setScrapInputs,
                              index,
                              "product_id",
                              event.target.value,
                            )
                          }
                        >
                          {options.scrap_products.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.code} — {item.name_ar}
                            </option>
                          ))}
                        </select>
                        <input
                          inputMode="decimal"
                          placeholder="كجم لكل خلطة"
                          value={line.quantity}
                          onChange={(event) =>
                            updateLine(
                              setScrapInputs,
                              index,
                              "quantity",
                              event.target.value,
                            )
                          }
                        />
                        <button
                          type="button"
                          className="mini-action"
                          onClick={() =>
                            setScrapInputs((current) =>
                              current.filter(
                                (_, lineIndex) => lineIndex !== index,
                              ),
                            )
                          }
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() =>
                        setScrapInputs((current) => [
                          ...current,
                          {
                            product_id: options.scrap_products[0]?.id || "",
                            quantity:
                              activeRecipe?.suggested_scrap_per_batch || "",
                          },
                        ])
                      }
                    >
                      <Plus size={15} /> مصدر كسر
                    </button>
                  </fieldset>
                  <label>
                    ملاحظات
                    <textarea
                      value={orderForm.notes}
                      onChange={(event) =>
                        setOrderForm({
                          ...orderForm,
                          notes: event.target.value,
                        })
                      }
                    />
                  </label>
                  <button
                    className="primary-button"
                    disabled={submitting || !orderForm.recipe_id}
                  >
                    {editingOrderId ? <Pencil size={16} /> : <Plus size={16} />} {editingOrderId ? "حفظ تعديلات المسودة" : "إنشاء الأمر"}
                  </button>
                </form>
              </article>
            ) : null}
          </section>

          {selected ? (
            <section className="panel manufacturing-detail">
              <header className="panel__head">
                <div>
                  <h3>
                    {selected.order_number} — {selected.recipe_name_ar}
                  </h3>
                  <p>
                    هدف {number.format(Number(selected.target_weight_kg))} كجم ·
                    مخطط{" "}
                    {number.format(Number(selected.planned_input_weight_kg))}{" "}
                    كجم
                  </p>
                </div>
                <em
                  className={`manufacturing-status manufacturing-status--${selected.status}`}
                >
                  {statusLabels[selected.status]}
                </em>
              </header>
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>الخامة</th>
                      <th>نوعها</th>
                      <th>لكل خلطة</th>
                      <th>المخطط</th>
                      <th>المصروف</th>
                      <th>المستخدم</th>
                      <th>المرتجع</th>
                      <th>التكلفة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.materials.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.product_name_ar}</strong>
                          <small>{item.product_code}</small>
                        </td>
                        <td>
                          {item.component_kind === "scrap"
                            ? "كسر اختياري"
                            : "خامة أساسية"}
                        </td>
                        <td>
                          {number.format(Number(item.quantity_per_batch))}
                        </td>
                        <td>{number.format(Number(item.planned_quantity))}</td>
                        <td>{number.format(Number(item.issued_quantity))}</td>
                        <td>{number.format(Number(item.used_quantity))}</td>
                        <td>{number.format(Number(item.returned_quantity))}</td>
                        <td>
                          {money.format(
                            Number(item.used_cost || item.issued_cost),
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {canManage ? (
                <div className="manufacturing-actions">
                  {selected.status === "draft" ? (
                    <>
                      <button
                        className="secondary-button"
                        disabled={submitting}
                        onClick={() => editOrder(selected)}
                      >
                        <Pencil size={16} /> تعديل المسودة
                      </button>
                      <button
                        className="secondary-button"
                        disabled={submitting}
                        onClick={() => void replan(selected)}
                      >
                        <RefreshCw size={16} /> إعادة تخطيط الكسر
                      </button>
                      <button
                        className="primary-button"
                        disabled={submitting}
                        onClick={() => void start(selected)}
                      >
                        <Play size={16} /> بدء وصرف الخامات
                      </button>
                      <button
                        className="danger-button"
                        disabled={submitting}
                        onClick={() => void removeDraft(selected)}
                      >
                        <Trash2 size={16} /> حذف المسودة
                      </button>
                    </>
                  ) : null}
                  {selected.status === "in_progress" ? (
                    <button
                      className="danger-button"
                      disabled={submitting}
                      onClick={() => void cancel(selected)}
                    >
                      <RotateCcw size={16} /> إلغاء ورد الخامات
                    </button>
                  ) : null}
                </div>
              ) : null}
              {selected.status === "in_progress" && canManage ? (
                <form
                  className="manufacturing-completion"
                  onSubmit={(event) => void complete(event)}
                >
                  <header>
                    <span>
                      <Scale size={19} />
                    </span>
                    <div>
                      <strong>الإكمال الفعلي</strong>
                      <small>
                        سجّل الخلطات والإنتاج السليم والمعيب والوزن والهالك.
                      </small>
                    </div>
                  </header>
                  <div className="manufacturing-completion__base">
                    <label>
                      الخلطات الفعلية
                      <input
                        required
                        type="number"
                        min="1"
                        value={completion.actual_batches}
                        onChange={(event) =>
                          setCompletion({
                            ...completion,
                            actual_batches: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      وزن الهالك كجم
                      <input
                        inputMode="decimal"
                        value={completion.scrap_weight_kg}
                        onChange={(event) =>
                          setCompletion({
                            ...completion,
                            scrap_weight_kg: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      ملاحظات
                      <input
                        value={completion.notes}
                        onChange={(event) =>
                          setCompletion({
                            ...completion,
                            notes: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>
                  <div className="manufacturing-output-grid">
                    {selected.outputs.map((item) => {
                      const values = completionOutputs[item.product_id] || {
                        good: "",
                        defective: "0",
                        weight: "",
                      };
                      return (
                        <article key={item.id}>
                          <strong>{item.product_name_ar}</strong>
                          <small>المخطط {item.planned_quantity} قطعة</small>
                          <label>
                            السليم
                            <input
                              inputMode="decimal"
                              value={values.good}
                              onChange={(event) =>
                                setCompletionOutputs((current) => ({
                                  ...current,
                                  [item.product_id]: {
                                    ...values,
                                    good: event.target.value,
                                  },
                                }))
                              }
                            />
                          </label>
                          <label>
                            المعيب
                            <input
                              inputMode="decimal"
                              value={values.defective}
                              onChange={(event) =>
                                setCompletionOutputs((current) => ({
                                  ...current,
                                  [item.product_id]: {
                                    ...values,
                                    defective: event.target.value,
                                  },
                                }))
                              }
                            />
                          </label>
                          <label>
                            الوزن الفعلي
                            <input
                              inputMode="decimal"
                              value={values.weight}
                              onChange={(event) =>
                                setCompletionOutputs((current) => ({
                                  ...current,
                                  [item.product_id]: {
                                    ...values,
                                    weight: event.target.value,
                                  },
                                }))
                              }
                            />
                          </label>
                        </article>
                      );
                    })}
                  </div>
                  <fieldset className="manufacturing-adjustments">
                    <legend>الخلطات المعدلة — اختياري</legend>
                    {adjustments.map((item, index) => (
                      <article key={index}>
                        <button
                          type="button"
                          className="mini-action"
                          onClick={() =>
                            setAdjustments((current) =>
                              current.filter(
                                (_, itemIndex) => itemIndex !== index,
                              ),
                            )
                          }
                        >
                          <X size={15} />
                        </button>
                        <label>
                          الخامة المستبعدة
                          <select
                            value={item.excluded_product_id}
                            onChange={(event) =>
                              setAdjustments((current) =>
                                current.map((row, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...row,
                                        excluded_product_id: event.target.value,
                                      }
                                    : row,
                                ),
                              )
                            }
                          >
                            {selected.materials.map((material) => (
                              <option
                                key={material.product_id}
                                value={material.product_id}
                              >
                                {material.product_name_ar}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          عدد الخلطات
                          <input
                            type="number"
                            min="1"
                            value={item.batch_count}
                            onChange={(event) =>
                              setAdjustments((current) =>
                                current.map((row, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...row,
                                        batch_count: event.target.value,
                                      }
                                    : row,
                                ),
                              )
                            }
                          />
                        </label>
                        <label>
                          السبب
                          <input
                            required
                            value={item.reason}
                            onChange={(event) =>
                              setAdjustments((current) =>
                                current.map((row, itemIndex) =>
                                  itemIndex === index
                                    ? { ...row, reason: event.target.value }
                                    : row,
                                ),
                              )
                            }
                          />
                        </label>
                        <div className="manufacturing-adjustment-quantities">
                          {selected.materials
                            .filter(
                              (material) =>
                                material.product_id !==
                                item.excluded_product_id,
                            )
                            .map((material) => (
                              <label key={material.product_id}>
                                {material.product_name_ar}
                                <input
                                  inputMode="decimal"
                                  placeholder="الافتراضي"
                                  value={
                                    item.quantities[material.product_id] || ""
                                  }
                                  onChange={(event) =>
                                    setAdjustments((current) =>
                                      current.map((row, itemIndex) =>
                                        itemIndex === index
                                          ? {
                                              ...row,
                                              quantities: {
                                                ...row.quantities,
                                                [material.product_id]:
                                                  event.target.value,
                                              },
                                            }
                                          : row,
                                      ),
                                    )
                                  }
                                />
                              </label>
                            ))}
                        </div>
                      </article>
                    ))}
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() =>
                        setAdjustments((current) => [
                          ...current,
                          {
                            excluded_product_id:
                              selected.materials[0]?.product_id || "",
                            batch_count: "1",
                            reason: "",
                            quantities: {},
                          },
                        ])
                      }
                    >
                      <Plus size={15} /> مجموعة تعديل
                    </button>
                  </fieldset>
                  <button
                    className="primary-button manufacturing-complete-button"
                    disabled={submitting}
                  >
                    <PackageCheck size={17} /> اعتماد الإكمال وإضافة الإنتاج
                  </button>
                </form>
              ) : null}
              {selected.status === "completed" ? (
                <>
                  <div className="manufacturing-summary">
                    <span>
                      <small>تكلفة الخامات</small>
                      <strong>
                        {money.format(Number(selected.material_cost))} ج.م
                      </strong>
                    </span>
                    <span>
                      <small>تكلفة الإنتاج السليم</small>
                      <strong>
                        {money.format(Number(selected.finished_cost))} ج.م
                      </strong>
                    </span>
                    <span>
                      <small>وزن الهالك</small>
                      <strong>
                        {number.format(
                          Number(selected.completion?.scrap_weight_kg || 0),
                        )}{" "}
                        كجم
                      </strong>
                    </span>
                    <span>
                      <small>فرق الوزن الرقابي</small>
                      <strong>
                        {number.format(Number(selected.weight_variance_kg))} كجم
                      </strong>
                    </span>
                  </div>
                  {selected.completion?.adjustments.length ? (
                    <div className="manufacturing-mix-report">
                      <header>
                        <strong>تقرير الخلطات المعدلة</strong>
                        <small>
                          {selected.completion.full_batches} كاملة ·{" "}
                          {selected.completion.modified_batches} معدلة
                        </small>
                      </header>
                      {selected.completion.adjustments.map((item) => (
                        <article key={item.id}>
                          <span>
                            <strong>
                              بدون {item.excluded_product_name_ar}
                            </strong>
                            <small>
                              {item.batch_count} خلطة · {item.reason}
                            </small>
                          </span>
                          <span>
                            <small>الكميات الفعلية</small>
                            <b>
                              {item.actual_material_quantities
                                .map(
                                  (value) =>
                                    `${value.product_name_ar}: ${value.actual_quantity}`,
                                )
                                .join(" · ") || "وفق المقادير القياسية"}
                            </b>
                          </span>
                          <em>{money.format(Number(item.cost_amount))} ج.م</em>
                        </article>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : null}
            </section>
          ) : null}
        </>
      )}
    </AppShell>
  );
}
