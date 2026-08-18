type BrandMarkProps = {
  compact?: boolean;
  inverse?: boolean;
};

export function BrandMark({ compact = false, inverse = false }: BrandMarkProps) {
  return (
    <div className={`brand ${inverse ? "brand--inverse" : ""}`} aria-label="PipeERP">
      <span className="brand__symbol" aria-hidden="true">
        <span />
      </span>
      {!compact ? (
        <span className="brand__copy">
          <strong>PipeERP</strong>
          <small>إدارة المصنع بوضوح</small>
        </span>
      ) : null}
    </div>
  );
}
