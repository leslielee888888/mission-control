import type { AssignmentStatus, MissionStatus } from "../api/types";
import { assignmentStatusLabel, missionStatusLabel } from "../lib/format";

const MISSION_STYLES: Record<MissionStatus, string> = {
  draft: "bg-draft-bg text-draft",
  pending_approval: "bg-pending-bg text-pending",
  approved: "bg-approved-bg text-approved",
  active: "bg-active-bg text-active",
  completed: "bg-completed-bg text-completed",
  cancelled: "bg-cancelled-bg text-cancelled",
};

const ASSIGNMENT_STYLES: Record<AssignmentStatus, string> = {
  proposed: "bg-pending-bg text-pending",
  confirmed: "bg-approved-bg text-approved",
  declined: "bg-declined-bg text-declined",
};

export function MissionStatusBadge({ status }: { status: MissionStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${MISSION_STYLES[status]}`}>
      {missionStatusLabel(status)}
    </span>
  );
}

export function AssignmentStatusBadge({ status }: { status: AssignmentStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${ASSIGNMENT_STYLES[status]}`}>
      {assignmentStatusLabel(status)}
    </span>
  );
}
