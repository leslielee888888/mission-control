import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { initials, roleLabel } from "../lib/format";

function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="1.75">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="2.5" fill="var(--color-accent)" stroke="none" />
      <path d="M12 3 a9 4 0 0 1 0 18 a9 4 0 0 1 0 -18" transform="rotate(35 12 12)" />
    </svg>
  );
}

export interface NavItem {
  key: string;
  label: string;
  icon: ReactNode;
}

export function Sidebar({
  items,
  activeKey,
  onSelect,
}: {
  items: NavItem[];
  activeKey: string;
  onSelect: (key: string) => void;
}) {
  const { user, logout } = useAuth();

  return (
    <div className="flex w-60 flex-none flex-col border-r border-border bg-surface p-4">
      <div className="flex items-center gap-2.5 px-2 pb-5">
        <Logo />
        <div className="text-[14.5px] font-bold">Mission Control</div>
      </div>

      <nav className="flex flex-col gap-0.5">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => onSelect(item.key)}
            aria-current={item.key === activeKey ? "page" : undefined}
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[13.5px] font-medium ${
              item.key === activeKey ? "bg-accent-2 text-accent-dark" : "text-text-2 hover:bg-surface-2"
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>

      <div className="flex-1" />

      {user && (
        <div className="flex items-center gap-2.5 border-t border-border px-2 py-2.5">
          <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-accent-2 text-xs font-bold text-accent-dark">
            {initials(user.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-semibold">{user.name}</div>
            <div className="text-[11px] text-text-3">{roleLabel(user.role)}</div>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Log out"
            title="Log out"
            className="flex-none text-text-3 hover:text-text-2"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

export const MissionsNavIcon = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9h18M8 4v5" />
  </svg>
);

export const AssignmentsNavIcon = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <path d="M9 12l2 2 4-4" />
    <circle cx="12" cy="12" r="9" />
  </svg>
);

export const CrewNavIcon = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <circle cx="9" cy="8" r="3.25" />
    <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
    <path d="M16.5 5.5a3.25 3.25 0 0 1 0 6.4M21.5 20a5.5 5.5 0 0 0-4.5-6.4" />
  </svg>
);

export const SkillsNavIcon = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <path d="M12 2.5l2.6 5.5 6 .8-4.4 4.3 1.1 6-5.3-2.9-5.3 2.9 1.1-6-4.4-4.3 6-.8z" />
  </svg>
);

export const ProfileNavIcon = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
    <circle cx="12" cy="8" r="3.75" />
    <path d="M4 20.5a8 8 0 0 1 16 0" />
  </svg>
);
