import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

export type SearchableSelectOption = {
  value: string;
  label: string;
  /** Extra text used when filtering (e.g. user id + name). Defaults to label. */
  searchText?: string;
};

type SearchableSelectProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SearchableSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  maxVisible?: number;
  hint?: string;
};

function matchesQuery(opt: SearchableSelectOption, q: string): boolean {
  if (!q) return true;
  const hay = (opt.searchText ?? opt.label).toLowerCase();
  return hay.includes(q);
}

export function SearchableSelect({
  label,
  value,
  onChange,
  options,
  placeholder = "Type to search…",
  disabled = false,
  maxVisible = 60,
  hint,
}: SearchableSelectProps) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);

  const selected = useMemo(
    () => options.find((o) => o.value === value) ?? null,
    [options, value],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? options.filter((o) => matchesQuery(o, q)) : options;
    return list.slice(0, maxVisible);
  }, [options, query, maxVisible]);

  const displayValue = open ? query : selected?.label ?? "";

  useEffect(() => {
    if (!open) return;
    function onDocDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, [open]);

  useEffect(() => {
    setHighlight(0);
  }, [query, open]);

  function pick(opt: SearchableSelectOption) {
    onChange(opt.value);
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
  }

  function onInputFocus() {
    if (disabled) return;
    setOpen(true);
    setQuery("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      setOpen(true);
      return;
    }
    if (!open) return;
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, Math.max(0, filtered.length - 1)));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    }
    if (e.key === "Enter" && filtered[highlight]) {
      e.preventDefault();
      pick(filtered[highlight]);
    }
  }

  const totalMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options.length;
    return options.filter((o) => matchesQuery(o, q)).length;
  }, [options, query]);

  return (
    <div className="searchable-select" ref={rootRef}>
      <label className="searchable-select-label" htmlFor={listId}>
        <span className="muted small">{label}</span>
        <div className={`searchable-select-control${open ? " open" : ""}${disabled ? " disabled" : ""}`}>
          <input
            ref={inputRef}
            id={listId}
            type="text"
            role="combobox"
            aria-expanded={open}
            aria-controls={`${listId}-listbox`}
            aria-autocomplete="list"
            autoComplete="off"
            disabled={disabled}
            placeholder={selected ? selected.label : placeholder}
            value={displayValue}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={onInputFocus}
            onKeyDown={onKeyDown}
          />
          <button
            type="button"
            className="searchable-select-chevron"
            tabIndex={-1}
            disabled={disabled}
            aria-label={open ? "Close list" : "Open list"}
            onClick={() => {
              if (disabled) return;
              if (open) {
                setOpen(false);
                setQuery("");
              } else {
                setOpen(true);
                setQuery("");
                inputRef.current?.focus();
              }
            }}
          >
            ▾
          </button>
        </div>
      </label>
      {hint ? <p className="muted small searchable-select-hint">{hint}</p> : null}
      {open && !disabled ? (
        <ul
          id={`${listId}-listbox`}
          role="listbox"
          className="searchable-select-list"
          aria-label={label}
        >
          {filtered.length === 0 ? (
            <li className="searchable-select-empty muted small">No matches</li>
          ) : (
            filtered.map((opt, i) => (
              <li key={opt.value || "__empty"} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={opt.value === value}
                  className={`searchable-select-option${i === highlight ? " highlighted" : ""}${opt.value === value ? " selected" : ""}`}
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => pick(opt)}
                >
                  {opt.label}
                </button>
              </li>
            ))
          )}
          {totalMatches > filtered.length ? (
            <li className="searchable-select-more muted small">
              + {totalMatches - filtered.length} more — keep typing to narrow down
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
