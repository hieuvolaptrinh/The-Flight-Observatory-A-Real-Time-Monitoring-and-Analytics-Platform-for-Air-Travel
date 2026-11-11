"use client";

import { useEffect, useRef, useState } from "react";
import { IconName } from "../flight-types";
import { Icon } from "./icons";

export interface SelectOption {
  value: string;
  label: string;
}

interface CustomSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  ariaLabel: string;
  icon?: IconName;
  size?: "default" | "compact";
  highlightActive?: boolean;
}

export function CustomSelect({
  value,
  onChange,
  options,
  ariaLabel,
  icon,
  size = "default",
  highlightActive = false,
}: CustomSelectProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const selectedOption = options.find(o => o.value === value) || options[0];
  const isFiltered = highlightActive && value !== "all";

  useEffect(() => {
    if (!open) return;

    function handleClickOutside(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div
      ref={wrapRef}
      className={`custom-select ${size === "compact" ? "compact" : ""} ${open ? "is-open" : ""}`}
    >
      <button
        type="button"
        className={`custom-select-trigger ${isFiltered ? "has-value" : ""}`}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(v => !v)}
      >
        {icon && (
          <span className="custom-select-icon">
            <Icon name={icon} size={14} />
          </span>
        )}
        <span className="custom-select-label">{selectedOption?.label ?? value}</span>
        <span className={`custom-select-chevron ${open ? "rotated" : ""}`}>
          <Icon name="chevron" size={13} />
        </span>
      </button>

      {open && (
        <div className="custom-select-menu" role="listbox" aria-label={ariaLabel}>
          {options.map(opt => {
            const selected = opt.value === value;
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={selected}
                className={`custom-select-option ${selected ? "selected" : ""}`}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
              >
                <span className="custom-select-option-text">{opt.label}</span>
                {selected && (
                  <span className="custom-select-check">
                    <Icon name="check" size={13} />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
