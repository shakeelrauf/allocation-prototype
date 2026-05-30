import { useMemo } from "react";
import { formatSelectUserOption } from "../utils/userDisplay";
import type { UserRow } from "../types";
import { SearchableSelect, type SearchableSelectOption } from "./SearchableSelect";

type UserSearchSelectProps = {
  label: string;
  value: string;
  onChange: (userId: string) => void;
  users: UserRow[];
  /** When set, adds a blank-value option (e.g. “Everyone”). */
  everyoneLabel?: string;
  disabled?: boolean;
  hint?: string;
  placeholder?: string;
};

export function UserSearchSelect({
  label,
  value,
  onChange,
  users,
  everyoneLabel,
  disabled,
  hint,
  placeholder = "Search by name or user id…",
}: UserSearchSelectProps) {
  const options = useMemo((): SearchableSelectOption[] => {
    const sorted = [...users].sort((a, b) =>
      formatSelectUserOption(a.user_id, a.user_name, a.tier)
        .toLowerCase()
        .localeCompare(formatSelectUserOption(b.user_id, b.user_name, b.tier).toLowerCase()),
    );
    const rows: SearchableSelectOption[] = [];
    if (everyoneLabel != null) {
      rows.push({ value: "", label: everyoneLabel, searchText: "everyone all" });
    }
    for (const u of sorted) {
      const labelText = formatSelectUserOption(u.user_id, u.user_name, u.tier);
      rows.push({
        value: u.user_id,
        label: labelText,
        searchText: `${u.user_id} ${u.user_name ?? ""} ${u.tier} ${labelText}`.toLowerCase(),
      });
    }
    return rows;
  }, [users, everyoneLabel]);

  return (
    <SearchableSelect
      label={label}
      value={value}
      onChange={onChange}
      options={options}
      placeholder={users.length === 0 ? "No users loaded" : placeholder}
      disabled={disabled || users.length === 0}
      hint={hint ?? (users.length === 0 ? "Import users on Dashboard first." : undefined)}
      maxVisible={80}
    />
  );
}
