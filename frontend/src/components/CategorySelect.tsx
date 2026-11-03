import type { Category } from "../api";

type Props = {
  categories: Category[];
  value: number | null;
  onChange: (id: number | null) => void;
  emptyLabel?: string;
  id?: string;
  "aria-label"?: string;
};

export default function CategorySelect({ categories, value, onChange, emptyLabel = "— sem categoria —", ...rest }: Props) {
  const active = categories.filter((c) => c.ativa);
  const tops = active.filter((c) => c.parent_id === null);
  return (
    <select
      {...rest}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
    >
      <option value="">{emptyLabel}</option>
      {tops.map((p) => {
        const kids = active.filter((c) => c.parent_id === p.id);
        return kids.length ? (
          <optgroup key={p.id} label={p.nome}>
            <option value={p.id}>{p.nome} (geral)</option>
            {kids.map((k) => (
              <option key={k.id} value={k.id}>
                {k.nome}
              </option>
            ))}
          </optgroup>
        ) : (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        );
      })}
    </select>
  );
}
